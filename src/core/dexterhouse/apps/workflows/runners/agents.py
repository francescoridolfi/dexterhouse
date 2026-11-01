# SPDX-License-Identifier: AGPL-3.0-or-later
"""`AgentsTurnRunner`: the `TurnRunner` that runs real agent turns (agents app, E-03).

One step run is one agent turn. The turn is created with `queue_turn(step_run_id, attempt)`
and run synchronously in the `run_step` worker (`agents` queue). A retry or a recovery after
a killed worker resumes the turn of the previous attempt when it is still alive (`queued`
or `running`), or returns its stored output when it completed: completed LLM and tool calls
are never paid or executed twice (ADR-0013). Only a turn that ended `failed` gets a new
`AgentTurn` for the new attempt. The turn stores the output artifacts; the engine reads
them back through `StepRun.agent_turn`.

Select it with `WORKFLOWS_TURN_RUNNER =
"dexterhouse.apps.workflows.runners.agents.AgentsTurnRunner"`.
"""

import structlog

from dexterhouse.apps.agents.models import AgentInstance, AgentStatus, AgentTurn, TurnStatus
from dexterhouse.apps.agents.services import (
    AgentTurnFailedError,
    TransientTurnError,
    queue_turn,
    run_turn,
)
from dexterhouse.apps.workflows.engine import common
from dexterhouse.apps.workflows.models import StepRun
from dexterhouse.apps.workflows.runner import TurnFailedError, TurnRequest
from dexterhouse.apps.workflows.runners.inputs import build_inputs
from dexterhouse_schema import TurnOutput

logger = structlog.get_logger(__name__)
ENDED = (TurnStatus.FAILED, TurnStatus.CANCELLED)


class AgentsTurnRunner:
    """Implements `TurnRunner` with `agents.services.queue_turn` + `run_turn`."""

    requires_packages = True  # projects do not start without a package per role

    def run(self, request: TurnRequest) -> TurnOutput:
        step_run = StepRun.objects.select_related("project", "phase_run", "agent", "task").get(
            pk=request.step_run_id
        )
        agent = self._agent(step_run)
        if not agent.package_path:
            raise TurnFailedError(
                "configuration", f"no agent package installed for role {agent.role}"
            )
        turn = self._turn(step_run, request, agent)
        StepRun.objects.filter(pk=step_run.pk, attempts=request.attempt).update(agent_turn=turn)
        try:
            return run_turn(turn.id)
        except AgentTurnFailedError as exc:
            raise TurnFailedError(exc.error_code or "failed", exc.detail) from exc
        except TransientTurnError as exc:
            # The turn stays `running`: the engine's next attempt resumes it.
            raise TurnFailedError("provider_unavailable", str(exc)) from exc

    @staticmethod
    def _agent(step_run: StepRun) -> AgentInstance:
        """The step's agent, or the role's current one if it was released meanwhile."""
        if step_run.agent.status != AgentStatus.RELEASED:
            return step_run.agent
        agent = common.agent_for(step_run.project, step_run.role)
        StepRun.objects.filter(pk=step_run.pk).update(agent=agent)
        return agent

    @staticmethod
    def _turn(step_run: StepRun, request: TurnRequest, agent: AgentInstance) -> AgentTurn:
        previous = (
            AgentTurn.objects.filter(step_run=step_run, agent_instance=agent)
            .order_by("-step_attempt")
            .first()
        )
        if previous is not None and previous.status not in ENDED:
            if previous.step_attempt != request.attempt:
                logger.info(
                    "workflows.turn_resumed",
                    step_run_id=str(step_run.id),
                    turn_id=str(previous.id),
                    attempt=request.attempt,
                )
            return previous
        task = request.task
        purpose = f"{request.phase_id}: {request.step}" + (f" {task.external_id}" if task else "")
        return queue_turn(
            agent=agent,
            purpose=purpose,
            inputs=build_inputs(request, step_run),
            phase_run_id=step_run.phase_run_id,
            task_id=step_run.task_id,
            step=request.step,
            enqueue=False,
            step_run_id=step_run.id,
            attempt=request.attempt,
        )
