# SPDX-License-Identifier: AGPL-3.0-or-later
"""The boundary between the workflow engine and the agents runtime (E-03).

The engine asks for one agent turn at a time with a :class:`TurnRequest` and expects a
validated :class:`~dexterhouse_schema.TurnOutput` back. `step_run_id` is the idempotency
key: a retried or recovered turn carries the same id with a higher `attempt`, so the
runtime can resume the persisted `AgentTurn` instead of paying for it twice (ADR-0013).
The implementation is chosen by `settings.WORKFLOWS_TURN_RUNNER`.
"""

import uuid
from typing import Any, Literal, Protocol

from django.conf import settings
from django.utils.module_loading import import_string
from pydantic import BaseModel, ConfigDict

from dexterhouse_schema import TurnContext, TurnOutput

VerdictRule = Literal["review", "test", "none"]


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TaskBrief(_Frozen):
    """The task a loop step works on (implementation phase)."""

    id: uuid.UUID
    external_id: str
    kind: Literal["feature", "fix"]
    title: str
    description: str
    acceptance: list[str]
    iteration: int
    max_iterations: int
    branch: str | None
    previous_result: dict[str, Any] | None = None


class Answer(_Frozen):
    question_id: str
    answer: str


class TurnRequest(_Frozen):
    """Everything the engine knows about the turn it wants; context building is E-03's."""

    step_run_id: uuid.UUID
    attempt: int
    organization_id: uuid.UUID
    project_id: uuid.UUID
    process: str
    phase_id: str
    step: str
    role: str
    agent_id: uuid.UUID
    execution_mode: Literal["supervised", "autonomous"]
    may_ask: bool
    produces: list[str]
    verdict_rule: VerdictRule
    round: int
    brief: str
    stack: dict[str, Any] | None = None
    task: TaskBrief | None = None
    comment: str | None = None
    answers: list[Answer] = []
    notes: list[str] = []

    def turn_context(self) -> TurnContext:
        return TurnContext(verdict=self.verdict_rule)


class TurnFailedError(Exception):
    """The turn could not produce a valid output; the engine retries it (max attempts)."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


class TurnRunner(Protocol):
    def run(self, request: TurnRequest) -> TurnOutput:
        """Run (or resume) the turn and return its validated output.

        Raises:
            TurnFailedError: the turn failed; the engine decides whether to retry.
        """
        ...


def get_runner() -> TurnRunner:
    return import_string(settings.WORKFLOWS_TURN_RUNNER)()


def verdict_rule(role: str) -> VerdictRule:
    return {"reviewer": "review", "tester": "test"}.get(role, "none")  # type: ignore[return-value]
