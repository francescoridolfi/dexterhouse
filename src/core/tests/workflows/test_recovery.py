# SPDX-License-Identifier: AGPL-3.0-or-later
"""ADR-0013: a worker killed in the middle of a phase loses and duplicates no turn."""

import os
import signal
import subprocess  # nosec B404: starts a Celery worker for the test
import sys
import time
from collections import Counter
from datetime import timedelta
from urllib.parse import urlsplit, urlunsplit

import pytest
from celery import Celery
from django.conf import settings as django_settings
from django.db import connection
from django.utils import timezone

from dexterhouse.apps.agents.models import AgentTurn
from dexterhouse.apps.events.models import Event
from dexterhouse.apps.gateway.models import LLMCall
from dexterhouse.apps.projects.models import Artifact
from dexterhouse.apps.workflows import tasks
from dexterhouse.apps.workflows.engine import steps
from dexterhouse.apps.workflows.models import StepRun, StepRunStatus
from dexterhouse.apps.workflows.runners.fake import FakeTurnRunner
from tests.conftest import TEAM_PACKAGES, install_test_packages
from tests.workflows.agents_runtime import use_fake_profiles
from tests.workflows.conftest import DyingRunner, KilledError, drain

RUN_STEP = "dexterhouse.apps.workflows.tasks.run_step"


def assert_each_turn_applied_once(project) -> None:
    rows = StepRun.objects.filter(project=project)
    assert set(rows.values_list("status", flat=True)) == {StepRunStatus.COMPLETED}
    keys = Counter(
        (r.phase_run_id, r.stage, r.step_index, r.round, r.iteration, r.task_id) for r in rows
    )
    assert max(keys.values()) == 1, "a turn was run twice"
    phase_steps = rows.filter(task__isnull=True).count()
    task_steps = rows.filter(task__isnull=False).count()
    events = Counter(Event.objects.filter(project_id=project.id).values_list("type", flat=True))
    assert events["phase.step.completed"] == phase_steps
    assert events["task.step.completed"] == task_steps
    assert set(Artifact.objects.filter(project=project).values_list("version", flat=True)) == {1}


def assert_no_duplicate_agent_turns(project, stuck) -> None:
    """The killed turn was resumed (not paid twice): one AgentTurn per step run."""
    turns = AgentTurn.objects.filter(project=project)
    assert turns.count() == StepRun.objects.filter(project=project).count()
    assert set(turns.values_list("status", flat=True)) == {"completed"}
    resumed = turns.get(step_run=stuck)
    assert (resumed.step_attempt, resumed.attempt) == (1, 2)  # created once, run twice
    keys = LLMCall.objects.filter(project=project, status="ok").values_list(
        "idempotency_key", flat=True
    )
    assert max(Counter(keys).values()) == 1


@pytest.mark.django_db
def test_simulated_kill_mid_turn_is_recovered_once(started, settings):
    settings.WORKFLOWS_FAKE_RUNNER = {"ask_questions": False, "tasks": 1}
    settings.WORKFLOWS_TURN_RUNNER = "tests.workflows.conftest.DyingRunner"
    DyingRunner.died = set()
    project = started(execution_mode="autonomous")
    with pytest.raises(KilledError):
        drain(project)
    stuck = StepRun.objects.get(project=project, status=StepRunStatus.RUNNING)
    assert (stuck.role, stuck.attempts) == ("architect", 1)
    steps.run_step(stuck.id)  # a duplicate delivery while the lease is valid is ignored
    stuck.refresh_from_db()
    assert (stuck.status, stuck.attempts) == ("running", 1)

    later = timezone.now() + timedelta(seconds=settings.WORKFLOWS_STEP_LEASE_S + 1)
    assert steps.reconcile(now=later) == 1
    StepRun.objects.filter(pk=stuck.pk).update(lease_expires_at=timezone.now())
    steps.run_step(stuck.id)
    stuck.refresh_from_db()
    assert (stuck.status, stuck.attempts) == ("completed", 2)
    drain(project)
    project.refresh_from_db()
    assert project.status == "completed"
    assert_each_turn_applied_once(project)


@pytest.mark.django_db
def test_late_worker_cannot_apply_a_taken_over_turn(started, settings):
    settings.WORKFLOWS_FAKE_RUNNER = {"ask_questions": False}
    project = started(execution_mode="autonomous")
    step = StepRun.objects.get(project=project)
    first = steps.claim(step.id)
    StepRun.objects.filter(pk=step.pk).update(lease_expires_at=timezone.now())
    second = steps.claim(step.id)
    assert (first.attempt, second.attempt) == (1, 2)
    output = FakeTurnRunner().run(second)
    steps.complete(step.id, first.attempt, output)  # stale: ignored
    step.refresh_from_db()
    assert step.status == "running"
    steps.complete(step.id, second.attempt, output)
    steps.complete(step.id, second.attempt, output)  # duplicate: ignored
    assert Artifact.objects.filter(project=project, kind="requirements").count() == 1


def _broker_url() -> str:
    parts = urlsplit(django_settings.REDIS_URL)
    return urlunsplit(parts._replace(path="/15"))


def _start_worker(log_path, env) -> subprocess.Popen:
    argv = [sys.executable, "-m", "celery", "-A", "dexterhouse", "worker", "-Q", "agents"]
    argv += ["-P", "solo", "--without-gossip", "--without-mingle", "--without-heartbeat"]
    return subprocess.Popen(  # noqa: S603  # nosec B603: fixed argv of the test worker
        argv, env=env, stdout=log_path.open("ab"), stderr=subprocess.STDOUT
    )


def _wait(predicate, timeout_s: float, what: str) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {what}")


@pytest.mark.slow
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("runner", ["fake", "agents"])
def test_killing_a_real_worker_mid_phase_loses_and_duplicates_nothing(
    started, monkeypatch, tmp_path, runner, organization, settings
):
    broker = _broker_url()
    sender = Celery(broker=broker)
    sender.connection_for_write().default_channel.client.flushdb()
    monkeypatch.setattr(
        tasks.run_step,
        "delay",
        lambda step_id: sender.send_task(RUN_STEP, args=[step_id], queue="agents"),
    )
    db = connection.settings_dict
    env = os.environ | {
        "DJANGO_SETTINGS_MODULE": "tests.workflows.worker_settings",
        "DH_TEST_BROKER_URL": broker,
        "DH_TEST_DB_NAME": db["NAME"],
        "DH_TEST_TURN_RUNNER": runner,
        "DATABASE_URL": f"postgres://{db['USER']}@{db['HOST']}:{db['PORT']}/{db['NAME']}",
    }
    if runner == "agents":
        install_test_packages(TEAM_PACKAGES, replace=True)  # the team hired at start
        use_fake_profiles(organization)
    log = tmp_path / "worker.log"
    worker = _start_worker(log, env)
    try:
        project = started(execution_mode="autonomous")

        def architect_running():
            if runner == "agents":  # killed inside the turn, after its first message
                return AgentTurn.objects.filter(
                    project=project, step_run__role="architect", status="running"
                ).exists()
            return StepRun.objects.filter(
                project=project, role="architect", status=StepRunStatus.RUNNING
            ).exists()

        _wait(architect_running, 60, "the architecture turn to start")
        worker.send_signal(signal.SIGKILL)
        worker.wait(10)
        stuck = StepRun.objects.get(project=project, status=StepRunStatus.RUNNING)
        assert stuck.attempts == 1

        def expired():
            return StepRun.objects.filter(pk=stuck.pk, lease_expires_at__lt=timezone.now()).exists()

        _wait(expired, 10, "the lease to expire")
        assert steps.reconcile() >= 1  # what the beat entry does every minute
        worker = _start_worker(log, env)

        def done():
            project.refresh_from_db()
            return project.status in ("completed", "failed")

        _wait(done, 90, "the project to finish")
        assert project.status == "completed", log.read_text()[-3000:]
        stuck.refresh_from_db()
        assert (stuck.status, stuck.attempts) == ("completed", 2)
        assert_each_turn_applied_once(project)
        if runner == "agents":
            assert_no_duplicate_agent_turns(project, stuck)
    finally:
        worker.kill()
        worker.wait(10)
