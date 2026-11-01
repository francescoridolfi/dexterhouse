# SPDX-License-Identifier: AGPL-3.0-or-later
"""Human in the loop (F-004, E-06): gate payloads, modes, questions, escalations, TTL, notes."""

from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from dexterhouse.apps.memory import tasks as memory_tasks
from dexterhouse.apps.notifications.models import Notification
from dexterhouse.apps.projects.models import Artifact, Note
from dexterhouse.apps.projects.services import notes
from dexterhouse.apps.workflows import escalations, reminders, services
from dexterhouse.apps.workflows.models import Gate, PhaseRun, StepRun, Task
from dexterhouse.apps.workflows.runners.fake import FakeTurnRunner
from dexterhouse.common.errors import InvalidTransitionError, ValidationFailedError
from tests.workflows.conftest import drain, event_types, events, open_gate

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def no_questions(settings):
    settings.WORKFLOWS_FAKE_RUNNER = {"ask_questions": False, "tasks": 1}


@pytest.fixture
def indexed(monkeypatch):
    """Capture what goes to the project memory instead of embedding it."""
    calls = []
    monkeypatch.setattr(
        memory_tasks.index_comment_task, "delay", lambda *a, **kw: calls.append((a, kw))
    )
    return calls


def phase(project, phase_id):
    return PhaseRun.objects.get(process_run__project=project, phase_id=phase_id)


def test_supervised_gate_blocks_with_payload_and_notifies(started, user, make_member):
    make_member("admin", "marta")
    make_member("member", "mario")
    make_member("viewer", "vera")
    project = started()
    drain(project)
    project.refresh_from_db()
    assert (project.status, project.waiting_reason) == ("waiting", "gate")
    gate = open_gate(project)
    assert gate.gate_id == "approve_requirements"
    kinds = {a["kind"] for a in gate.payload["artifacts"]}
    assert kinds == {"requirements", "user_stories"}
    first = gate.payload["artifacts"][0]
    assert first["produced_by_role"] == "analyst"
    assert first["name"].endswith(".md")
    step = StepRun.objects.filter(project=project, role="analyst").last()
    assert gate.payload["produced_by"]["step_run_id"] == str(step.id)
    assert gate.payload["produced_by"]["role"] == "analyst"
    opened = events(project, "gate.opened")[0].payload
    assert set(opened["artifacts"][0]) == {"id", "kind", "version"}
    deciders = Notification.objects.filter(gate=gate)
    assert sorted(deciders.values_list("user__username", flat=True)) == ["ada", "marta"]
    created = events(project, "notification.created")
    assert {e.payload["user_id"] for e in created} == {str(n.user_id) for n in deciders}
    assert created[0].payload["gate_type"] == "approval"
    services.decide(gate.id, user, decision="approve")
    assert not Notification.objects.filter(gate=gate, read_at__isnull=True).exists()


def test_email_notification_when_enabled(
    started, user, settings, django_capture_on_commit_callbacks
):
    settings.NOTIFICATIONS_EMAIL_ENABLED = True
    settings.NOTIFICATIONS_PUBLIC_URL = "https://dh.example/"
    user.email = "ada@example.com"
    user.save()
    project = started()
    with django_capture_on_commit_callbacks(execute=True):
        drain(project)
    gate = open_gate(project)
    assert len(mail.outbox) == 1
    sent = mail.outbox[0]
    assert sent.to == ["ada@example.com"]
    assert "Approve analysis" in sent.subject
    assert f"https://dh.example/projects/{project.id}?gate={gate.id}" in sent.body
    note = Notification.objects.get(gate=gate)
    assert note.emailed_at is not None
    from dexterhouse.apps.notifications.services import send_email

    assert send_email(note.id) is False  # once only


def test_no_email_by_default(started, django_capture_on_commit_callbacks, user):
    user.email = "ada@example.com"
    user.save()
    project = started()
    with django_capture_on_commit_callbacks(execute=True):
        drain(project)
    assert mail.outbox == []
    assert Notification.objects.filter(project=project).count() == 1


def test_autonomous_auto_approves_traced_but_always_required_blocks(started, user):
    project = started(
        execution_mode="autonomous", gate_overrides={"approve_plan": "always_required"}
    )
    drain(project)
    gate = open_gate(project)
    assert gate.gate_id == "approve_plan"
    auto = Gate.objects.filter(project=project, status="auto_approved")
    assert set(auto.values_list("gate_id", flat=True)) == {
        "approve_requirements",
        "approve_architecture",
    }
    assert all(g.decided_by_id is None and g.decision == "approve" for g in auto)
    decided = [e.payload for e in events(project, "gate.decided")]
    assert all(d["auto"] and d["decided_by"] is None for d in decided)
    assert not Notification.objects.filter(gate__in=auto).exists()
    assert Notification.objects.filter(gate=gate).count() == 1


def test_question_gate_emits_agent_question_asked(started, user, settings):
    settings.WORKFLOWS_FAKE_RUNNER = {"tasks": 1}
    project = started()
    drain(project)
    gate = open_gate(project)
    assert gate.type == "question"
    asked = events(project, "agent.question.asked")
    assert len(asked) == 1
    step = StepRun.objects.get(project=project, role="analyst")
    assert asked[0].payload["gate_id"] == str(gate.id)
    assert asked[0].payload["turn_id"] == str(step.id)  # fake runner: no AgentTurn
    assert asked[0].actor_type == "agent"
    assert [q["id"] for q in asked[0].payload["questions"]] == [
        q["id"] for q in gate.payload["questions"]
    ]
    answers = [{"question_id": q["id"], "answer": "yes"} for q in gate.payload["questions"]]
    assert services.decide(gate.id, user, answers=answers)[1] == "phase_resumed"
    assert phase(project, "analysis").context["answers"][0]["answer"] == "yes"


def test_autonomous_questions_become_an_assumptions_artifact(started, settings, monkeypatch):
    """An agent that still waits for answers in autonomous mode gets its defaults assumed."""
    settings.WORKFLOWS_FAKE_RUNNER = {"tasks": 1}
    asks = FakeTurnRunner._asks
    monkeypatch.setattr(
        FakeTurnRunner,
        "_asks",
        lambda self, r: asks(self, r.model_copy(update={"execution_mode": "supervised"})),
    )
    project = started(execution_mode="autonomous")
    drain(project)
    assert not Gate.objects.filter(project=project, type="question").exists()
    assumptions = Artifact.objects.get(project=project, name="assumptions.md")
    assert assumptions.data["assumptions"][0]["id"] == "a1"
    assert "# Assumptions" in assumptions.content
    project.refresh_from_db()
    assert project.status == "completed"


def test_gate_comments_are_indexed_with_the_higher_weight(
    started, user, indexed, django_capture_on_commit_callbacks
):
    project = started()
    drain(project)
    gate = open_gate(project)
    with django_capture_on_commit_callbacks(execute=True):
        services.decide(gate.id, user, decision="approve", comment="FIFO waiting list")
    assert indexed == [
        (
            (str(project.organization_id), str(project.id), str(gate.id), "FIFO waiting list"),
            {"kind": "gate_comment"},
        )
    ]
    gate = open_gate(project) or Gate.objects.none()
    drain(project)
    gate = open_gate(project)
    with django_capture_on_commit_callbacks(execute=True):
        services.decide(gate.id, user, decision="approve")
    assert len(indexed) == 1  # no comment, nothing indexed


def test_gate_ttl_reminds_without_deciding(started, organization, make_member):
    make_member("admin", "marta")
    organization.settings = {"gate_ttl_hours": 2}
    organization.save()
    project = started()
    drain(project)
    gate = open_gate(project)
    assert gate.expires_at is not None
    opened = events(project, "gate.opened")[0].payload
    assert opened["expires_at"] is not None
    assert reminders.remind_gates(timezone.now()) == 0
    later = gate.expires_at + timedelta(minutes=1)
    assert reminders.remind_gates(later) == 1
    gate.refresh_from_db()
    assert (gate.status, gate.reminders) == ("open", 1)
    assert gate.expires_at == later + timedelta(hours=2)
    assert reminders.remind_gates(gate.expires_at) == 1
    assert event_types(project, "gate.expired") == ["gate.expired"]
    renotified = [e.payload["times"] for e in events(project, "gate.renotified")]
    assert renotified == [1, 2]
    sent = Notification.objects.filter(gate=gate, kind="gate_reminder")
    assert sent.count() == 4  # two deciders, two reminders
    assert sent.first().title.startswith("Reminder: ")


def test_escalate_service_budget_blocks_and_retry_resumes(started, user):
    project = started()
    with pytest.raises(ValueError, match="unknown escalation reason"):
        escalations.escalate(project, "bored")
    gate = escalations.escalate(project, "budget_exceeded", {"spent": "20.1", "budget": "20"})
    again = escalations.escalate(project.id, "budget_exceeded", {"spent": "20.2"})
    assert again.id == gate.id
    project.refresh_from_db()
    assert (project.status, project.waiting_reason) == ("waiting", "budget")
    assert gate.payload["details"] == {"spent": "20.1", "budget": "20"}
    assert gate.payload["reason"] == "budget_exceeded"
    waiting = events(project, "project.waiting")[-1].payload
    assert waiting == {"reason": "budget", "gate_id": str(gate.id)}
    assert drain(project) == 0
    with pytest.raises(ValidationFailedError, match="escalation gate"):
        services.decide(gate.id, user, decision="approve")
    _, next_ = services.decide(gate.id, user, decision="retry", comment="budget raised")
    assert next_ == "phase_resumed"
    project.refresh_from_db()
    assert project.status == "running"
    assert events(project, "project.resumed")[-1].payload == {"reason": "budget"}
    drain(project)
    assert open_gate(project).gate_id == "approve_requirements"


def test_escalate_needs_a_running_process(make_project):
    project = make_project()
    with pytest.raises(InvalidTransitionError):
        escalations.escalate(project, "budget_exceeded")


def test_high_risk_tool_escalation_retry_reruns_the_step_with_the_tool(started, user):
    project = started()
    step = StepRun.objects.get(project=project, status="queued")
    gate = escalations.escalate(
        project, "tool_high_risk", {"tool": "workspace.exec", "args": {"cmd": "rm"}}
    )
    assert gate.payload["step_index"] == step.step_index
    assert phase(project, "analysis").status == "waiting_gate"
    assert not escalations.tool_approved(gate.phase_run_id, "workspace.exec")
    drain(project)
    assert StepRun.objects.get(pk=step.pk).status == "queued"  # project waiting: no turn
    services.decide(gate.id, user, decision="retry")
    assert escalations.tool_approved(gate.phase_run_id, "workspace.exec")
    assert not escalations.tool_approved(gate.phase_run_id, "workspace.other")
    assert not escalations.tool_approved(None, "workspace.exec")
    drain(project)
    assert open_gate(project).gate_id == "approve_requirements"


def test_escalation_accept_keeps_going_and_drop_fails(started, user):
    project = started()
    gate = escalations.escalate(project, "security", {"summary": "3 violations"})
    assert gate.payload["summary"] == "3 violations"
    assert services.decide(gate.id, user, decision="accept")[1] == "phase_resumed"
    gate = escalations.escalate(project, "security")
    assert services.decide(gate.id, user, decision="drop")[1] == "phase_failed"
    project.refresh_from_db()
    assert project.status == "failed"


def test_escalation_mid_turn_waits_for_the_question_gate(started, user, settings):
    """An escalation decided while another gate of the phase is open does not resume it."""
    settings.WORKFLOWS_FAKE_RUNNER = {"tasks": 1}
    project = started()
    gate = escalations.escalate(project, "budget_exceeded")
    services.decide(gate.id, user, decision="retry")
    drain(project)
    question = open_gate(project)
    assert question.type == "question"
    budget = escalations.escalate(project, "budget_exceeded")
    services.decide(budget.id, user, decision="retry")
    assert phase(project, "analysis").status == "waiting_gate"


def test_task_escalation_retry_note_enters_the_context(started, user, settings):
    settings.WORKFLOWS_FAKE_RUNNER = {
        "ask_questions": False,
        "tasks": 1,
        "verdicts": {"reviewer:T-01": ["request_changes"] * 3},
    }
    project = started(execution_mode="autonomous")
    drain(project)
    gate = open_gate(project)
    assert gate.payload["reason"] == "task_exhausted"
    services.decide(gate.id, user, decision="retry", comment="Use a lock on the booking row")
    assert phase(project, "implementation").context["comment"] == ("Use a lock on the booking row")
    step = StepRun.objects.filter(project=project, role="developer").order_by("-created_at")[0]
    assert step.status == "queued"
    drain(project)
    step.refresh_from_db()
    assert step.request["comment"] == "Use a lock on the booking row"


def test_release_reject_creates_fix_tasks_listed_in_the_response(started, user, client):
    project = started(
        execution_mode="autonomous", gate_overrides={"approve_release": "always_required"}
    )
    drain(project)
    gate = open_gate(project)
    assert gate.gate_id == "approve_release"
    body = {"decision": "reject", "comment": "1. Fix the header\n2. Fix the footer"}
    data = client.post(f"/api/v1/gates/{gate.id}/decide", body, format="json").json()
    assert data["next"] == "tasks_created"
    assert [t["title"] for t in data["tasks_created"]] == ["Fix the header", "Fix the footer"]
    assert all(t["kind"] == "fix" for t in data["tasks_created"])
    implementation = phase(project, "implementation")
    assert implementation.context["comment"].startswith("1. Fix the header")
    drain(project)
    fixes = Task.objects.filter(project=project, kind="fix", parent__isnull=True)
    assert set(fixes.values_list("status", flat=True)) == {"done"}


def test_notes_to_the_team_enter_the_context_and_memory(
    started, user, client, indexed, django_capture_on_commit_callbacks
):
    project = started()
    url = f"/api/v1/projects/{project.id}/notes"
    with django_capture_on_commit_callbacks(execute=True):
        current = client.post(url, {"content": "Use Tailwind", "phase_run": "current"})
        everyone = client.post(url, {"content": "Write tests", "phase_run": None}, format="json")
    assert current.status_code == 201, current.json()
    analysis = phase(project, "analysis")
    assert current.json()["phase_run"] == str(analysis.id)
    assert everyone.json()["phase_run"] is None
    assert [kw for _, kw in indexed] == [{"kind": "note"}, {"kind": "note"}]
    assert client.post(url, {"content": "x", "phase_run": "nope"}).status_code == 400
    drain(project)
    step = StepRun.objects.get(project=project, role="analyst")
    assert step.request["notes"] == ["Use Tailwind", "Write tests"]
    consumed = events(project, "note.consumed")
    assert len(consumed) == 2
    assert consumed[0].payload["agent_id"] == str(step.agent_id)
    note = Note.objects.get(content="Use Tailwind")
    assert note.consumed_by_turn_ids == [step.id]
    listed = client.get(url).json()["results"]
    assert {n["consumed"] for n in listed} == {True}
    assert client.delete(f"/api/v1/notes/{note.id}").status_code == 409
    # Consumed once per turn: running the bookkeeping again changes nothing.
    assert notes.consume(project, [note.id], step.id, step.agent_id, "analyst") == []


def test_note_to_the_current_phase_needs_a_running_phase(make_project, client):
    project = make_project()
    url = f"/api/v1/projects/{project.id}/notes"
    response = client.post(url, {"content": "hello", "phase_run": "current"})
    assert response.status_code == 409
