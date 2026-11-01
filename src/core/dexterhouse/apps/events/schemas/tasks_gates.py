# SPDX-License-Identifier: AGPL-3.0-or-later
"""task.*, gate.*, question.* payloads (contracts/events/tasks_gates.md)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from dexterhouse.apps.events.schemas.base import EventPayload
from dexterhouse.apps.events.schemas.common import ArtifactRef, _Strict

TaskStep = Literal["developer", "reviewer", "tester"]
Verdict = Literal["approve", "request_changes", "pass", "fail"]
GateType = Literal["approval", "question", "escalation"]

# task.*


class TaskCreated(EventPayload):
    event_type = "task.created"
    actors = ("agent", "system", "user")

    task_id: uuid.UUID
    external_id: str
    kind: Literal["feature", "fix"]
    parent_id: uuid.UUID | None = None
    iteration: int
    title: str
    assigned_role: str
    depends_on: list[uuid.UUID]
    estimate: Literal["S", "M", "L"]


class TaskUpdated(EventPayload):
    event_type = "task.updated"
    actors = ("user",)

    task_id: uuid.UUID
    changes: dict[str, Any]


class TaskReady(EventPayload):
    event_type = "task.ready"

    task_id: uuid.UUID


class TaskStarted(EventPayload):
    event_type = "task.started"

    task_id: uuid.UUID
    agent_id: uuid.UUID
    branch: str
    iteration: int


class TaskStepCompleted(EventPayload):
    event_type = "task.step.completed"
    actors = ("agent",)

    task_id: uuid.UUID
    step: TaskStep
    agent_id: uuid.UUID
    verdict: Verdict | None = None
    artifact: ArtifactRef


class TaskIteration(EventPayload):
    event_type = "task.iteration"

    task_id: uuid.UUID
    iteration: int
    max_iterations: int
    reason: Literal["review", "tests", "human"]
    fix_task_id: uuid.UUID
    findings_count: int | None = None


class TaskCompleted(EventPayload):
    event_type = "task.completed"

    task_id: uuid.UUID
    iterations: int
    duration_s: float
    cost: Decimal
    merged_commit: str
    forced: bool


class TaskAttempt(_Strict):
    iteration: int
    step: TaskStep
    verdict: Verdict
    summary: str


class TaskEscalated(EventPayload):
    event_type = "task.escalated"

    task_id: uuid.UUID
    gate_id: uuid.UUID
    attempts: list[TaskAttempt]


class TaskCancelled(EventPayload):
    event_type = "task.cancelled"
    actors = ("user", "system")

    task_id: uuid.UUID
    reason: str


# gate.*


class GateOpened(EventPayload):
    event_type = "gate.opened"
    actors = ("system", "agent")

    gate_id: uuid.UUID
    type: GateType
    phase_id: str
    task_id: uuid.UUID | None = None
    title: str
    summary: str
    artifacts: list[ArtifactRef]
    expires_at: datetime | None = None


class DecidedBy(_Strict):
    id: uuid.UUID
    name: str


class GateDecided(EventPayload):
    event_type = "gate.decided"
    actors = ("user", "system")

    gate_id: uuid.UUID
    type: GateType
    decision: Literal["approve", "reject", "approve_with_comments", "retry", "accept", "drop"]
    comment: str | None = None
    decided_by: DecidedBy | None  # required, null when auto-approved
    auto: bool
    next: Literal[
        "phase_completed",
        "phase_reopened",
        "tasks_created",
        "phase_failed",
        "task_retried",
        "task_accepted",
        "task_dropped",
        "escalated",
    ]


class GateRenotified(EventPayload):
    event_type = "gate.renotified"

    gate_id: uuid.UUID
    times: int


class GateExpired(EventPayload):
    event_type = "gate.expired"

    gate_id: uuid.UUID


# question.*


class Answer(_Strict):
    question_id: str
    answer: str


class QuestionAnswered(EventPayload):
    event_type = "question.answered"
    actors = ("user",)

    gate_id: uuid.UUID
    answers: list[Answer]
