# SPDX-License-Identifier: AGPL-3.0-or-later
"""Interpreter semantics: reopen rounds, rejects, loop iterations, escalations, failures."""

import pytest

from dexterhouse.apps.agents.models import AgentInstance
from dexterhouse.apps.projects.models import Artifact
from dexterhouse.apps.projects.services import lifecycle
from dexterhouse.apps.workflows import services
from dexterhouse.apps.workflows.models import Gate, PhaseRun, StepRun, Task
from dexterhouse.common.errors import InvalidTransitionError, ValidationFailedError
from tests.workflows.conftest import drain, event_types, events, open_gate

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def no_questions(settings):
    settings.WORKFLOWS_FAKE_RUNNER = {"ask_questions": False}


def run_until_gate(project, gate_id=None):
    drain(project)
    gate = open_gate(project)
    assert gate is not None
    if gate_id:
        assert gate.gate_id == gate_id
    return gate


def approve_until(project, user, stop: str):
    """Approve every approval gate until `stop` opens (returned, not decided)."""
    for _ in range(10):
        gate = run_until_gate(project)
        if gate.gate_id == stop:
            return gate
        services.decide(gate.id, user, decision="approve")
    raise AssertionError(stop)


def phase(project, phase_id):
    return PhaseRun.objects.get(process_run__project=project, phase_id=phase_id)


def test_approve_with_comments_reopens_then_escalates_after_two_rounds(started, user):
    project = started()
    gate = run_until_gate(project, "approve_requirements")
    _, next_ = services.decide(gate.id, user, decision="approve_with_comments", comment="FIFO")
    assert next_ == "phase_reopened"
    analysis = phase(project, "analysis")
    assert (analysis.round, analysis.reopen_count) == (1, 1)
    gate = run_until_gate(project, "approve_requirements")
    assert gate.payload["round"] == 1
    requirements = Artifact.objects.filter(project=project, kind="requirements")
    assert sorted(requirements.values_list("version", flat=True)) == [1, 2]
    assert "Addresses: FIFO" in requirements.get(version=2).content
    services.decide(gate.id, user, decision="approve_with_comments", comment="again")
    gate = run_until_gate(project, "approve_requirements")
    _, next_ = services.decide(gate.id, user, decision="approve_with_comments", comment="3rd")
    assert next_ == "escalated"
    escalation = open_gate(project)
    assert (escalation.type, escalation.payload["reason"]) == ("escalation", "rounds_exhausted")
    _, next_ = services.decide(escalation.id, user, decision="accept")
    assert next_ == "phase_completed"
    assert phase(project, "analysis").status == "completed"
    assert "phase.reopened" in event_types(project)


def test_escalation_retry_reopens_and_drop_fails(started, user):
    project = started()
    for comment in ("a", "b", "c"):
        gate = run_until_gate(project, "approve_requirements")
        services.decide(gate.id, user, decision="approve_with_comments", comment=comment)
    escalation = open_gate(project)
    assert services.decide(escalation.id, user, decision="retry")[1] == "phase_reopened"
    gate = run_until_gate(project, "approve_requirements")
    services.decide(gate.id, user, decision="approve_with_comments", comment="d")
    escalation = open_gate(project)
    assert services.decide(escalation.id, user, decision="drop")[1] == "phase_failed"
    project.refresh_from_db()
    assert project.status == "failed"


def test_reject_reopens_with_the_comment_then_escalates_after_two_rounds(started, user):
    """F-004: `reject` reopens the phase like `approve_with_comments` (max 2 rounds)."""
    project = started()
    gate = run_until_gate(project, "approve_requirements")
    with pytest.raises(ValidationFailedError):
        services.decide(gate.id, user, decision="reject", comment="")
    assert services.decide(gate.id, user, decision="reject", comment="no")[1] == "phase_reopened"
    analysis = phase(project, "analysis")
    assert analysis.status in ("reopened", "running")
    assert (analysis.reopen_count, analysis.context["comment"]) == (1, "no")
    gate = run_until_gate(project, "approve_requirements")
    requests = StepRun.objects.filter(project=project, role="analyst").order_by("seq")
    assert requests.last().request["comment"] == "no"
    services.decide(gate.id, user, decision="reject", comment="still no")
    gate = run_until_gate(project, "approve_requirements")
    assert services.decide(gate.id, user, decision="reject", comment="3rd")[1] == "escalated"
    escalation = open_gate(project)
    assert escalation.payload["reason"] == "rounds_exhausted"
    assert services.decide(escalation.id, user, decision="drop")[1] == "phase_failed"
    project.refresh_from_db()
    assert project.status == "failed"


def test_decisions_are_validated_and_single_shot(started, user):
    project = started()
    gate = run_until_gate(project, "approve_requirements")
    with pytest.raises(ValidationFailedError):
        services.decide(gate.id, user, decision="retry")
    with pytest.raises(ValidationFailedError):
        services.decide(gate.id, user, decision="approve_with_comments", comment=" ")
    services.decide(gate.id, user, decision="approve")
    with pytest.raises(InvalidTransitionError, match="already decided by ada"):
        services.decide(gate.id, user, decision="approve")


def test_question_gate_requires_every_answer(started, user, settings):
    settings.WORKFLOWS_FAKE_RUNNER = {}
    project = started()
    gate = run_until_gate(project, "question")
    with pytest.raises(ValidationFailedError) as err:
        services.decide(gate.id, user, answers=[{"question_id": "q1", "answer": "No"}])
    assert err.value.errors[0]["field"] == "answers.q2"
    assert gate.payload["questions"][0]["id"] == "q1"
    opened = events(project, "gate.opened")[0]
    assert (opened.actor_type, opened.actor_name) == ("agent", "analyst")


def test_reject_release_creates_fix_tasks_and_reopens_implementation(started, user):
    project = started()
    gate = approve_until(project, user, "approve_release")
    comment = "1. The booking page crashes\n2. Emails are sent twice"
    _, next_ = services.decide(gate.id, user, decision="reject", comment=comment)
    assert next_ == "tasks_created"
    fixes = Task.objects.filter(project=project, kind="fix", parent__isnull=True)
    assert sorted(fixes.values_list("external_id", flat=True)) == ["T-04", "T-05"]
    assert fixes.get(external_id="T-04").title == "The booking page crashes"
    assert phase(project, "release").status == "reopened"
    gate = run_until_gate(project, "approve_release")
    assert set(fixes.values_list("status", flat=True)) == {"done"}
    assert gate.payload["round"] == 1
    services.decide(gate.id, user, decision="approve")
    drain(project)
    project.refresh_from_db()
    assert project.status == "completed"


def test_review_and_test_failures_iterate_with_fix_children(started, user, settings):
    settings.WORKFLOWS_FAKE_RUNNER = {
        "ask_questions": False,
        "tasks": 1,
        "verdicts": {"reviewer:T-01": ["request_changes"], "tester:T-01": ["pass", "fail"]},
    }
    project = started(execution_mode="autonomous")
    drain(project)
    project.refresh_from_db()
    assert project.status == "completed"
    task = Task.objects.get(project=project, parent__isnull=True)
    assert (task.iteration, task.status) == (3, "done")
    children = task.children.order_by("iteration")
    assert [(c.iteration, c.kind, c.status) for c in children] == [
        (2, "fix", "done"),
        (3, "fix", "done"),
    ]
    reasons = [e.payload["reason"] for e in events(project, "task.iteration")]
    assert reasons == ["review", "tests"]
    steps = StepRun.objects.filter(task=task).order_by("seq")
    assert [(s.iteration, s.step) for s in steps] == [
        (1, "developer"),
        (1, "reviewer"),
        (2, "developer"),
        (2, "reviewer"),
        (2, "tester"),
        (3, "developer"),
        (3, "reviewer"),
        (3, "tester"),
    ]


@pytest.fixture
def escalated(started, settings):
    settings.WORKFLOWS_FAKE_RUNNER = {
        "ask_questions": False,
        "tasks": 2,
        "verdicts": {"reviewer:T-01": ["request_changes"] * 4},
    }
    project = started(execution_mode="autonomous")
    drain(project)
    return project


def test_exhausted_task_escalates_and_retry_extends_iterations(escalated, user):
    project = escalated
    project.refresh_from_db()
    assert (project.status, project.waiting_reason) == ("waiting", "gate")
    gate = open_gate(project)
    task = Task.objects.get(project=project, external_id="T-01", parent__isnull=True)
    assert (gate.type, gate.task_id, task.status) == ("escalation", task.id, "escalated")
    assert len(gate.payload["attempts"]) == 3
    assert event_types(project, "task.escalated")
    _, next_ = services.decide(gate.id, user, decision="retry")
    assert next_ == "task_retried"
    drain(project)
    task.refresh_from_db()
    assert (task.max_iterations, task.iteration) == (4, 4)
    gate = open_gate(project)
    assert services.decide(gate.id, user, decision="accept")[1] == "task_accepted"
    drain(project)
    project.refresh_from_db()
    assert project.status == "completed"
    forced = [e.payload["forced"] for e in events(project, "task.completed")]
    assert forced == [True, False]


def test_dropping_an_escalated_task_cancels_its_dependents(escalated, user):
    project = escalated
    gate = open_gate(project)
    task = Task.objects.get(pk=gate.task_id)
    services.cancel_task(task.id, user)  # an escalated task is dropped through its gate
    statuses = dict(
        Task.objects.filter(project=project, parent__isnull=True).values_list(
            "external_id", "status"
        )
    )
    assert statuses == {"T-01": "cancelled", "T-02": "cancelled"}
    reasons = [e.payload["reason"] for e in events(project, "task.cancelled")]
    assert reasons == ["dropped by human", "dependency_cancelled"]
    drain(project)
    project.refresh_from_db()
    assert project.status == "completed"


def test_on_exhausted_fail_fails_the_phase(started, settings):
    from dexterhouse.apps.workflows.models import ProcessRun

    settings.WORKFLOWS_FAKE_RUNNER = {
        "ask_questions": False,
        "tasks": 1,
        "verdicts": {"tester:T-01": ["fail"] * 3},
    }
    project = started(
        execution_mode="autonomous", gate_overrides={"approve_plan": "always_required"}
    )
    drain(project)
    run = ProcessRun.objects.get(project=project)
    definition = run.definition
    next(p for p in definition["phases"] if p["id"] == "implementation")["on_exhausted"] = "fail"
    run.definition = definition
    run.save()
    from dexterhouse.apps.accounts.models import User

    services.decide(open_gate(project).id, User.objects.get(username="ada"), decision="approve")
    drain(project)
    project.refresh_from_db()
    assert project.status == "failed"
    assert phase(project, "implementation").error_code == "loop_exhausted"


def test_turn_failures_retry_then_escalate_and_retry_resumes(started, user, settings):
    """F-004: an error repeated 3 times opens a human escalation, even in autonomous mode."""
    settings.WORKFLOWS_FAKE_RUNNER = {"ask_questions": False, "fail": {"architect": 3}}
    project = started(execution_mode="autonomous")
    drain(project)
    project.refresh_from_db()
    assert (project.status, project.waiting_reason) == ("waiting", "gate")
    failed = StepRun.objects.get(project=project, status="failed")
    assert (failed.role, failed.attempts) == ("architect", 3)
    assert failed.error.startswith("provider_error")
    escalation = open_gate(project)
    assert (escalation.type, escalation.payload["reason"]) == ("escalation", "turn_failed")
    assert escalation.payload["details"]["role"] == "architect"
    assert phase(project, "architecture").status == "waiting_gate"
    settings.WORKFLOWS_FAKE_RUNNER = {"ask_questions": False}
    _, next_ = services.decide(escalation.id, user, decision="retry", comment="try again")
    assert next_ == "phase_resumed"
    drain(project)
    project.refresh_from_db()
    assert project.status == "completed"
    decided = events(project, "gate.decided")
    assert decided[-1].payload["next"] != "phase_resumed"  # later gates were auto-approved
    assert any(e.payload["next"] == "phase_resumed" for e in decided)


def test_turn_failure_escalation_accept_skips_the_step(started, user, settings):
    settings.WORKFLOWS_FAKE_RUNNER = {"ask_questions": False, "fail": {"architect": 3}}
    project = started(execution_mode="autonomous")
    drain(project)
    escalation = open_gate(project)
    settings.WORKFLOWS_FAKE_RUNNER = {"ask_questions": False}
    # `accept` skips the failed step; the phase `exit` then runs it again if it must.
    assert services.decide(escalation.id, user, decision="accept")[1] == "phase_resumed"
    drain(project)
    project.refresh_from_db()
    assert project.status == "completed"


def test_turn_failure_escalation_drop_fails_and_project_retry_resumes(started, user, settings):
    settings.WORKFLOWS_FAKE_RUNNER = {"ask_questions": False, "fail": {"architect": 3}}
    project = started(execution_mode="autonomous")
    drain(project)
    escalation = open_gate(project)
    assert services.decide(escalation.id, user, decision="drop")[1] == "phase_failed"
    project.refresh_from_db()
    assert project.status == "failed"
    settings.WORKFLOWS_FAKE_RUNNER = {"ask_questions": False}
    lifecycle.retry_project(project.id, user)
    drain(project)
    project.refresh_from_db()
    assert project.status == "completed"
    assert events(project, "project.retried")[0].payload == {"from_phase_id": "architecture"}


def test_pause_freezes_new_turns_and_resume_continues(started, user):
    project = started(execution_mode="autonomous")
    lifecycle.pause_project(project.id, user)
    assert drain(project) == 0
    assert StepRun.objects.filter(project=project, status="queued").count() == 1
    with pytest.raises(InvalidTransitionError):
        lifecycle.pause_project(project.id, user)
    lifecycle.resume_project(project.id, user)
    drain(project)
    project.refresh_from_db()
    assert project.status == "completed"
    assert "project.paused" in event_types(project)


def test_resume_with_open_gate_goes_back_to_waiting(started, user):
    project = started()
    run_until_gate(project, "approve_requirements")
    lifecycle.pause_project(project.id, user)
    lifecycle.resume_project(project.id, user)
    project.refresh_from_db()
    assert (project.status, project.waiting_reason) == ("waiting", "gate")


def test_hire_enables_the_replan_step(started, user, settings, team_packages):
    settings.WORKFLOWS_FAKE_RUNNER = {"ask_questions": False, "hire": True, "tasks": 1}
    project = started(execution_mode="autonomous")
    drain(project)
    project.refresh_from_db()
    assert project.status == "completed"
    planning = phase(project, "planning")
    assert planning.context["hired"] == ["htmx_frontend_developer"]
    hired = AgentInstance.objects.get(project=project, role="htmx_frontend_developer")
    assert (hired.package_name, hired.allowed_tools) == ("htmx-frontend-developer", [])
    team = AgentInstance.objects.filter(project=project).exclude(pk=hired.pk)
    assert all(a.package_path for a in team)  # packages found: no placeholders
    assert event_types(project, "agent.hired").count("agent.hired") == 8
    steps = StepRun.objects.filter(phase_run=planning).order_by("seq")
    assert [s.step for s in steps] == ["project_manager", "recruiter", "replan"]
    boards = Artifact.objects.filter(project=project, kind="task_board")
    assert sorted(boards.values_list("version", flat=True)) == [1, 2]


def test_failed_artifacts_exit_retries_then_escalates(started, user, monkeypatch):
    from dexterhouse.apps.workflows.runners import fake

    monkeypatch.setitem(fake.TEXT_NAMES, "user_stories", "stories.md")
    original = fake.FakeTurnRunner._output

    def without_stories(self, request):
        data = original(self, request)
        data["artifacts"] = [a for a in data["artifacts"] if a["kind"] != "user_stories"]
        return data

    monkeypatch.setattr(fake.FakeTurnRunner, "_output", without_stories)
    project = started()
    gate = run_until_gate(project)
    assert (gate.type, gate.payload["reason"]) == ("escalation", "exit_failed")
    checks = [e.payload for e in events(project, "phase.exit_checked")]
    assert [c["ok"] for c in checks] == [False, False, False]
    assert checks[0]["detail"] == "missing: user_stories"
    assert StepRun.objects.filter(project=project).count() == 3
    services.decide(gate.id, user, decision="retry")
    gate = run_until_gate(project)
    assert gate.payload["reason"] == "exit_failed"
    services.decide(gate.id, user, decision="accept")
    gate = run_until_gate(project)
    assert gate.gate_id == "approve_requirements"


def test_skip_and_add_task_and_edit_rules(started, user, settings):
    settings.WORKFLOWS_FAKE_RUNNER = {"ask_questions": False, "tasks": 1}
    project = started(gate_overrides={})
    retro = phase(project, "retrospective")
    services.skip_phase(retro.id, user)
    with pytest.raises(InvalidTransitionError):
        services.skip_phase(retro.id, user)
    with pytest.raises(InvalidTransitionError):
        services.add_task(project.id, user, {"title": "x", "acceptance": ["y"]})
    approve_until(project, user, "approve_release")
    implementation = phase(project, "implementation")
    assert implementation.status == "completed"
    assert Gate.objects.filter(project=project, status="open").count() == 1
    assert phase(project, "retrospective").status == "skipped"


def test_team_without_packages_is_hired_as_placeholders(started):
    from dexterhouse.apps.projects.services.snapshot import build_snapshot

    project = started(execution_mode="autonomous")
    team = AgentInstance.objects.filter(project=project)
    assert sorted(team.values_list("role", flat=True)) == sorted(
        ["analyst", "architect", "project_manager", "recruiter", "developer", "reviewer", "tester"]
    )
    assert {a.package_path for a in team} == {""}
    step = StepRun.objects.get(project=project)
    assert step.agent == team.get(role="analyst")
    agents = {a["role"]: a for a in build_snapshot(project)["agents"]}
    assert (agents["analyst"]["status"], agents["analyst"]["room"]) == ("working", "meeting_room")
    assert agents["tester"]["status"] == "idle"
    drain(project)
    tasks = Task.objects.filter(project=project)
    assert tasks.exists()
    assert {t.assigned_instance.role for t in tasks} == {"developer"}
