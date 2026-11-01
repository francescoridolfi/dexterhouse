# SPDX-License-Identifier: AGPL-3.0-or-later
"""A whole turn: Celery task, context, MCP tools, TurnOutput, idempotent resume."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from dexterhouse.apps.agents import tasks
from dexterhouse.apps.agents.models import AgentStatus, AgentTurn, ToolCall, TurnStatus
from dexterhouse.apps.agents.schemas import ArtifactInput, TaskInput, TurnInputs
from dexterhouse.apps.agents.services import (
    AgentTurnFailedError,
    TransientTurnError,
    cancel_turn,
    queue_turn,
    run_turn,
)
from dexterhouse.apps.agents.services import turns as turns_module
from dexterhouse.apps.events.models import Event
from dexterhouse.apps.gateway.models import LLMCall, ModelProfile
from dexterhouse.apps.gateway.providers.fake import FakeResponse

from .conftest import call, final

pytestmark = pytest.mark.django_db

INPUTS = TurnInputs(
    step_description="Analysis of the brief.",
    task=TaskInput(title="Requirements for GymBook", acceptance=["Booking rules are explicit"]),
    artifacts=[
        ArtifactInput(id=uuid.uuid4(), kind="brief", name="brief.md", content="A gym booking app.")
    ],
    room="analysis_room",
    may_ask=True,
)


class WorkerKilledError(BaseException):
    """Stands for SIGKILL: not an Exception, nothing catches it."""


def events(turn: AgentTurn) -> list[str]:
    return list(
        Event.objects.filter(correlation_id=turn.id)
        .order_by("created_at")
        .values_list("type", flat=True)
    )


def test_full_turn_through_the_celery_task(
    agent, script, echo_log, django_capture_on_commit_callbacks
):
    script(FakeResponse(text="Let me check.", tool_calls=[call("echo.say", text="hello")]), final())
    with django_capture_on_commit_callbacks(execute=True):
        turn = queue_turn(agent=agent, purpose="Write requirements", inputs=INPUTS, step="analysis")
    turn.refresh_from_db()
    assert turn.status == TurnStatus.COMPLETED
    assert turn.output["summary"] == "Wrote the requirements."
    assert turn.tool_calls_count == 1
    assert turn.messages[2]["parts"][1]["name"] == "echo.say"
    assert turn.messages[3]["parts"][0]["content"] == "echo: hello"
    assert echo_log() == [f"say {agent.project_id}"]
    manifest = turn.context_manifest
    assert manifest["profile"] == "balanced"
    assert manifest["cap"] == 60_000
    assert manifest["sections"]["artifacts"][0]["sections"] == "whole"
    assert manifest["skills"] == ["brief-reading", "markdown-artifacts"]  # package, then shared
    assert "echo.say" in manifest["tools"]
    assert "workspace.read" not in manifest["tools"]  # runner tool: not reachable yet
    assert turn.input_tokens > 0
    assert LLMCall.objects.filter(agent_turn_id=turn.id).count() == 2
    assert events(turn) == [
        "agent.turn.queued",
        "agent.moved",
        "agent.status",
        "agent.turn.started",
        "agent.tool.requested",
        "agent.tool.used",
        "agent.turn.completed",
        "agent.moved",
        "agent.status",
    ]
    agent.refresh_from_db()
    assert agent.status == AgentStatus.IDLE

    # Running it again changes nothing: same output, no new rows, no new tool execution.
    again = run_turn(turn.id)
    assert again.summary == "Wrote the requirements."
    assert ToolCall.objects.filter(agent_turn=turn).count() == 1
    assert LLMCall.objects.filter(agent_turn_id=turn.id).count() == 2
    assert len(echo_log()) == 1


def test_resume_after_worker_kill_does_not_repeat_tools_or_llm_calls(agent, script, echo_log):
    turn = queue_turn(agent=agent, purpose="p", inputs=INPUTS, enqueue=False)
    killer = FakeResponse(text="unused")
    provider = script(FakeResponse(tool_calls=[call("echo.say", text="once")]), killer)
    original = provider.stream

    def stream(request):
        if not provider.responses or provider.responses[0] is killer:
            raise WorkerKilledError
        return original(request)

    provider.stream = stream
    with pytest.raises(WorkerKilledError):
        run_turn(turn.id)
    turn.refresh_from_db()
    assert turn.status == TurnStatus.RUNNING
    assert ToolCall.objects.filter(agent_turn=turn).count() == 1
    assert LLMCall.objects.filter(agent_turn_id=turn.id).count() == 1

    provider.stream = original
    provider.responses[:] = [final()]
    output = run_turn(turn.id)
    turn.refresh_from_db()
    assert output.status == "done"
    assert turn.attempt == 2
    assert ToolCall.objects.filter(agent_turn=turn).count() == 1
    assert LLMCall.objects.filter(agent_turn_id=turn.id).count() == 2
    assert echo_log() == [f"say {agent.project_id}"]


def test_kill_between_llm_call_and_persisted_message_reuses_the_call(agent, script, monkeypatch):
    turn = queue_turn(agent=agent, purpose="p", inputs=INPUTS, enqueue=False)
    script(final(), FakeResponse(text="must not be used"))
    real_append = turns_module._append
    state = {"killed": False}

    def append(turn_obj, message, *fields):
        if message.role == "assistant" and not state["killed"]:
            state["killed"] = True
            raise WorkerKilledError
        real_append(turn_obj, message, *fields)

    monkeypatch.setattr(turns_module, "_append", append)
    with pytest.raises(WorkerKilledError):
        run_turn(turn.id)
    assert LLMCall.objects.filter(agent_turn_id=turn.id).count() == 1
    output = run_turn(turn.id)
    assert output.summary == "Wrote the requirements."
    assert LLMCall.objects.filter(agent_turn_id=turn.id).count() == 1


def test_interrupted_non_idempotent_tool_is_not_run_again(agent, script, echo_log):
    turn = queue_turn(agent=agent, purpose="p", inputs=INPUTS, enqueue=False)
    script(FakeResponse(tool_calls=[call("echo.write", path="a.txt", content="x")]), final())
    run_turn(turn.id)
    record = ToolCall.objects.get(agent_turn=turn)
    # Simulate a crash during the call: row pending, tool message never appended.
    record.status = "pending"
    record.save()
    turn.refresh_from_db()
    turn.status = TurnStatus.RUNNING
    turn.messages = turn.messages[:3]
    turn.output = None
    turn.save()
    script(final())
    run_turn(turn.id)
    record.refresh_from_db()
    assert record.status == "error"
    assert "interrupted" in record.result["content"]
    assert echo_log().count(f"write {agent.project_id}") == 1


def test_invalid_output_is_reprompted_then_fails(agent, script):
    turn = queue_turn(agent=agent, purpose="p", inputs=INPUTS, enqueue=False)
    bad_kind = final(artifacts=[{"kind": "architecture", "name": "a.md", "content": "x"}])
    script(FakeResponse(text="no json here"), bad_kind, final())
    output = run_turn(turn.id)
    turn.refresh_from_db()
    assert output.status == "done"
    assert turn.reprompts == 2
    assert "did not end with a JSON object" in turn.messages[3]["parts"][0]["text"]
    assert "not in output_contract" in turn.messages[5]["parts"][0]["text"]

    failing = queue_turn(agent=agent, purpose="p", inputs=INPUTS, enqueue=False)
    script(*[FakeResponse(text="nope")] * 3)
    with pytest.raises(AgentTurnFailedError) as info:
        run_turn(failing.id)
    assert info.value.error_code == "output_contract"
    assert events(failing)[-3:] == ["agent.turn.failed", "agent.moved", "agent.status"]
    with pytest.raises(AgentTurnFailedError):
        run_turn(failing.id)  # a failed turn stays failed


def test_refusal_and_truncation_are_reprompted(agent, script):
    turn = queue_turn(agent=agent, purpose="p", inputs=INPUTS, enqueue=False)
    script(
        FakeResponse(text="{", stop="max_tokens"), FakeResponse(text="", stop="refusal"), final()
    )
    assert run_turn(turn.id).status == "done"
    turn.refresh_from_db()
    assert turn.reprompts == 2


def test_tool_limit(agent, script):
    turn = queue_turn(agent=agent, purpose="p", inputs=INPUTS, enqueue=False)
    calls = [call("echo.say", call_id=f"c{i}", text="x") for i in range(5)]
    script(FakeResponse(tool_calls=calls))
    with pytest.raises(AgentTurnFailedError) as info:
        run_turn(turn.id)
    assert info.value.error_code == "tool_limit"
    assert ToolCall.objects.filter(agent_turn=turn).count() == 4  # limits.max_tool_calls


def test_three_refused_calls_fail_the_turn(agent, script):
    turn = queue_turn(agent=agent, purpose="p", inputs=INPUTS, enqueue=False)
    script(
        FakeResponse(tool_calls=[call("git.push", call_id="a")]),
        FakeResponse(tool_calls=[call("echo.say", call_id="b", text="x" * 100)]),  # args_policy
        FakeResponse(tool_calls=[call("marketplace.install", call_id="c")]),
    )
    with pytest.raises(AgentTurnFailedError) as info:
        run_turn(turn.id)
    assert info.value.error_code == "permission"
    kinds = list(
        Event.objects.filter(type="security.violation").values_list("payload__kind", flat=True)
    )
    assert sorted(kinds) == ["args_policy", "tool_not_allowed", "tool_not_allowed"]
    assert Event.objects.filter(type="security.turn_blocked").count() == 1


def test_tool_errors_are_reported_to_the_agent(agent, script):
    turn = queue_turn(agent=agent, purpose="p", inputs=INPUTS, enqueue=False)
    script(
        FakeResponse(
            tool_calls=[call("echo.fail"), call("workspace.read", call_id="c2", path="x")]
        ),
        final(),
    )
    run_turn(turn.id)
    turn.refresh_from_db()
    results = turn.messages[3]["parts"]
    assert results[0]["is_error"]
    assert "fail" in results[0]["content"]
    assert results[1]["is_error"]
    assert "tool_unavailable" in results[1]["content"]
    assert set(ToolCall.objects.filter(agent_turn=turn).values_list("status", flat=True)) == {
        "error"
    }


def test_data_residency_local_refuses_cloud_profiles(agent, script):
    ModelProfile.objects.filter(profile="balanced").update(
        provider="anthropic", model="claude-sonnet-5-5"
    )
    local = INPUTS.model_copy(update={"data_residency": "local"})
    turn = queue_turn(agent=agent, purpose="p", inputs=local, enqueue=False)
    with pytest.raises(AgentTurnFailedError) as info:
        run_turn(turn.id)
    assert info.value.error_code == "configuration"
    assert "data_residency" in info.value.detail
    assert LLMCall.objects.count() == 0


def test_transient_provider_error_keeps_the_turn_resumable(agent, script, monkeypatch):
    turn = queue_turn(agent=agent, purpose="p", inputs=INPUTS, enqueue=False)
    script(*[FakeResponse(error="error")] * 4)
    with pytest.raises(TransientTurnError):
        run_turn(turn.id)
    turn.refresh_from_db()
    assert turn.status == TurnStatus.RUNNING

    script(*[FakeResponse(error="error")] * 8)
    with pytest.raises(TransientTurnError):  # called directly, retry() re-raises
        tasks.run_turn_task.run(str(turn.id))
    assert Event.objects.filter(type="agent.turn.failed", payload__will_retry=True).exists()

    monkeypatch.setattr(tasks, "MAX_RETRIES", 0)
    assert tasks.run_turn_task.run(str(turn.id)) is None
    turn.refresh_from_db()
    assert (turn.status, turn.error_code) == (TurnStatus.FAILED, "provider")


def test_context_length_rebuilds_once(agent, script):
    turn = queue_turn(agent=agent, purpose="p", inputs=INPUTS, enqueue=False)
    script(FakeResponse(error="error", error_code="context_length"), final())
    assert run_turn(turn.id).status == "done"
    turn.refresh_from_db()
    assert turn.context_manifest["rebuilt"] is True
    assert turn.context_manifest["cap"] == 45_000


def test_timeout(agent, script):
    turn = queue_turn(agent=agent, purpose="p", inputs=INPUTS, enqueue=False)
    provider = script(FakeResponse(tool_calls=[call("echo.say", text="x")]))
    original = provider.stream

    def stream(request):
        if not provider.responses:
            raise WorkerKilledError
        return original(request)

    provider.stream = stream
    with pytest.raises(WorkerKilledError):
        run_turn(turn.id)
    AgentTurn.objects.filter(id=turn.id).update(started_at=timezone.now() - timedelta(hours=1))
    with pytest.raises(AgentTurnFailedError) as info:
        run_turn(turn.id)
    assert info.value.error_code == "timeout"


def test_cancel_only_queued_turns(agent):
    turn = queue_turn(agent=agent, purpose="p", inputs=INPUTS, enqueue=False)
    assert cancel_turn(turn.id, "project paused")
    assert not cancel_turn(turn.id, "again")
    with pytest.raises(AgentTurnFailedError):
        run_turn(turn.id)
    assert "agent.turn.cancelled" in events(turn)


def test_hired_agent_gets_the_intersection_of_tools(
    organization, project, fake_profiles, tool_dirs
):
    from dexterhouse.apps.agents.services import create_agent_instance

    from .conftest import FIXTURES

    instance = create_agent_instance(
        organization_id=organization.id,
        project_id=project.id,
        package_path=str(FIXTURES / "agents" / "test-analyst"),
        granted_tools=["echo.say", "git.push"],
        display_name="Analyst #2",
    )
    assert instance.allowed_tools == ["echo.say"]
    assert instance.room == "analysis_room"
    hired = Event.objects.get(type="agent.hired")
    assert hired.payload["package"] == {"name": "test-analyst", "version": "1.0.0"}
    assert str(instance) == "Analyst #2 (analyst)"


def test_broken_package_is_a_configuration_failure(agent, tmp_path):
    turn = queue_turn(agent=agent, purpose="p", inputs=INPUTS, enqueue=False)
    agent.package_path = str(tmp_path / "missing")
    agent.save()
    with pytest.raises(AgentTurnFailedError) as info:
        run_turn(turn.id)
    assert info.value.error_code == "configuration"


def test_queue_is_idempotent_per_step_run_and_attempt(agent, user):
    from dexterhouse.apps.projects.services import lifecycle
    from dexterhouse.apps.workflows.models import StepRun

    lifecycle.start_project(agent.project_id, user)
    step_run = StepRun.objects.get(project_id=agent.project_id).id
    first = queue_turn(agent=agent, purpose="p", inputs=INPUTS, enqueue=False, step_run_id=step_run)
    again = queue_turn(agent=agent, purpose="p", inputs=INPUTS, enqueue=False, step_run_id=step_run)
    retry = queue_turn(
        agent=agent, purpose="p", inputs=INPUTS, enqueue=False, step_run_id=step_run, attempt=2
    )
    assert first.id == again.id
    assert retry.id != first.id
    assert AgentTurn.objects.filter(step_run_id=step_run).count() == 2
