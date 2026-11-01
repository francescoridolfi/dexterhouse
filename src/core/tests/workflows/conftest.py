# SPDX-License-Identifier: AGPL-3.0-or-later
from collections.abc import Callable
from typing import Any

import pytest

from dexterhouse.apps.events.models import Event
from dexterhouse.apps.projects.models import Project
from dexterhouse.apps.projects.services import lifecycle
from dexterhouse.apps.projects.services.projects import create_project
from dexterhouse.apps.workflows.engine import steps
from dexterhouse.apps.workflows.models import Gate, GateStatus, StepRun, StepRunStatus
from dexterhouse.apps.workflows.runners.fake import FakeTurnRunner
from tests.live_runner import (  # noqa: F401 - the real runner, for test_e2e_runner (Docker)
    docker_client,
    egress_proxy,
    live_runner,
    runner_settings,
)

BRIEF = "A web app for a small gym: courses, members, bookings with a waiting list."


@pytest.fixture
def make_project(organization, user) -> Callable[..., Project]:
    def make(**overrides: Any) -> Project:
        data = {"name": "GymBook", "brief": BRIEF, "budget": "20", **overrides}
        return create_project(organization, user, data)

    return make


@pytest.fixture
def started(make_project, user) -> Callable[..., Project]:
    """Create and start a project (default: supervised software-house-default)."""

    def start(**overrides: Any) -> Project:
        project = make_project(**overrides)
        lifecycle.start_project(project.id, user)
        project.refresh_from_db()
        return project

    return start


def drain(project: Project, limit: int = 500) -> int:
    """Run queued steps one by one, as a worker would, until none is runnable."""
    ran = 0
    while ran < limit:
        project.refresh_from_db()
        step = (
            StepRun.objects.filter(project=project, status=StepRunStatus.QUEUED)
            .order_by("created_at")
            .first()
        )
        if step is None or project.status != "running":
            return ran
        steps.run_step(step.id)
        ran += 1
    raise AssertionError("drain did not settle")


def open_gate(project: Project) -> Gate | None:
    return Gate.objects.filter(project=project, status=GateStatus.OPEN).first()


def events(project: Project, prefix: str = "") -> list[Event]:
    rows = Event.objects.filter(project_id=project.id, type__startswith=prefix)
    return list(rows.order_by("created_at", "id"))


def event_types(project: Project, prefix: str = "") -> list[str]:
    return [e.type for e in events(project, prefix)]


class KilledError(BaseException):
    """Simulates a worker dying in the middle of a turn (not an Exception)."""


class DyingRunner(FakeTurnRunner):
    """Dies during the first turn of `role`, then behaves."""

    died: set[str] = set()  # noqa: RUF012 (shared on purpose across instances)
    role = "architect"

    def run(self, request):
        if request.role == self.role and request.role not in self.died:
            self.died.add(request.role)
            raise KilledError
        return super().run(request)


@pytest.fixture
def real_runtime(settings, organization, monkeypatch, team_packages):
    """`AgentsTurnRunner` + test agent packages + `fake` provider, MCP servers included.

    For transactional tests: the stdio MCP servers read the test database through the
    environment; `run_step` is not sent anywhere, `drain` runs the steps.
    """
    from django.db import connection

    from dexterhouse.apps.workflows import tasks
    from tests.workflows.agents_runtime import AGENTS_RUNNER, RESPONDER, use_fake_profiles

    db = connection.settings_dict
    monkeypatch.setenv(
        "DATABASE_URL", f"postgres://{db['USER']}@{db['HOST']}:{db['PORT']}/{db['NAME']}"
    )
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "dexterhouse.settings.test")
    monkeypatch.setattr(tasks.run_step, "delay", lambda step_id: None)
    settings.WORKFLOWS_TURN_RUNNER = AGENTS_RUNNER
    settings.GATEWAY_FAKE_RESPONDER = RESPONDER
    use_fake_profiles(organization)
