# SPDX-License-Identifier: AGPL-3.0-or-later
"""`AgentsTurnRunner` edge cases (the end-to-end runs are in `test_e2e_agents.py`)."""

import pytest

from dexterhouse.apps.agents.models import AgentInstance, AgentTurn, TurnStatus
from dexterhouse.apps.agents.services import AgentTurnFailedError, TransientTurnError
from dexterhouse.apps.workflows.engine import steps
from dexterhouse.apps.workflows.models import StepRun
from dexterhouse.apps.workflows.runner import TurnFailedError, TurnRequest
from dexterhouse.apps.workflows.runners import agents as runner_module
from dexterhouse.apps.workflows.runners.agents import AgentsTurnRunner
from dexterhouse.apps.workflows.runners.inputs import build_inputs, input_kinds, review_context
from tests.workflows.conftest import drain

pytestmark = pytest.mark.django_db


@pytest.fixture
def claimed(started, settings):
    def make(**overrides):
        settings.WORKFLOWS_FAKE_RUNNER = {"ask_questions": False}
        project = started(**overrides)
        step = StepRun.objects.get(project=project)
        return step, steps.claim(step.id)

    return make


def test_a_placeholder_agent_cannot_run_a_real_turn(claimed, no_packages):
    _, request = claimed()
    with pytest.raises(TurnFailedError) as info:
        AgentsTurnRunner().run(request)
    assert info.value.code == "configuration"


def test_failures_map_to_turn_failed_and_alive_turns_are_resumed(
    claimed, team_packages, monkeypatch
):
    step, request = claimed()

    def transient(turn_id):
        raise TransientTurnError("provider down")

    monkeypatch.setattr(runner_module, "run_turn", transient)
    with pytest.raises(TurnFailedError) as info:
        AgentsTurnRunner().run(request)
    assert info.value.code == "provider_unavailable"
    turn = AgentTurn.objects.get(step_run=step)
    step.refresh_from_db()
    assert step.agent_turn == turn
    assert turn.inputs["artifacts"][0]["kind"] == "brief"
    assert "Produce these artifacts: requirements, user_stories." in turn.inputs["step_description"]

    StepRun.objects.filter(pk=step.pk).update(status="queued")
    second = steps.claim(step.id)
    monkeypatch.setattr(runner_module, "run_turn", lambda turn_id: turn_id)
    assert AgentsTurnRunner().run(second) == turn.id  # same turn, not a new one

    AgentTurn.objects.filter(pk=turn.pk).update(status=TurnStatus.FAILED)

    def failed(turn_id):
        AgentTurn.objects.filter(pk=turn_id).update(
            status=TurnStatus.FAILED, error_code="output_contract", error_detail="bad json"
        )
        raise AgentTurnFailedError(AgentTurn.objects.get(pk=turn_id))

    StepRun.objects.filter(pk=step.pk).update(status="queued")
    third = steps.claim(step.id)
    monkeypatch.setattr(runner_module, "run_turn", failed)
    with pytest.raises(TurnFailedError) as info:
        AgentsTurnRunner().run(third)
    assert info.value.code == "output_contract"
    assert AgentTurn.objects.filter(step_run=step).count() == 2  # a fresh turn for attempt 3


def test_a_released_agent_is_replaced(claimed, team_packages, monkeypatch):
    step, request = claimed()
    AgentInstance.objects.filter(pk=step.agent_id).update(status="released")
    monkeypatch.setattr(runner_module, "run_turn", lambda turn_id: turn_id)
    AgentsTurnRunner().run(request)
    step.refresh_from_db()
    assert step.agent.role == "analyst"
    assert step.agent.status == "idle"
    assert AgentInstance.objects.filter(project=step.project, role="analyst").count() == 2


def test_inputs_of_loop_steps(started, settings):
    settings.WORKFLOWS_FAKE_RUNNER = {
        "ask_questions": False,
        "tasks": 1,
        "verdicts": {"reviewer:T-01": ["request_changes", "approve"]},
    }
    project = started(execution_mode="autonomous")
    drain(project)
    items, known = review_context(project.id, "T-01")
    assert known == ["R-1"]
    assert items == []  # the latest review approved
    developer = StepRun.objects.filter(project=project, step="developer").last()
    turn_request = TurnRequest.model_validate(developer.request)
    assert input_kinds(turn_request) == ("task_board", "stack", "architecture")
    inputs = build_inputs(turn_request, developer)
    assert inputs.task.external_id == "T-01"
    assert inputs.known_finding_ids is None
    assert inputs.stack_test_command == "uv run pytest -q"
    reviewer = StepRun.objects.filter(project=project, step="reviewer").last()
    review_inputs = build_inputs(TurnRequest.model_validate(reviewer.request), reviewer)
    assert review_inputs.known_finding_ids == ["R-1"]
    assert [a.kind for a in review_inputs.artifacts][-1] == "dev_notes"
    assert all("T-01" in a.name for a in review_inputs.artifacts if a.kind == "dev_notes")


def test_start_is_refused_without_a_package_per_role(make_project, user, settings, no_packages):
    from dexterhouse.apps.projects.services import lifecycle
    from dexterhouse.common.errors import ValidationFailedError

    settings.WORKFLOWS_TURN_RUNNER = "dexterhouse.apps.workflows.runners.agents.AgentsTurnRunner"
    project = make_project()
    with pytest.raises(ValidationFailedError) as info:
        lifecycle.start_project(project.id, user)
    assert "no agent package for role(s): analyst" in str(info.value.errors)
