# SPDX-License-Identifier: AGPL-3.0-or-later
"""project.*, process.*, phase.*, note.* payloads (contracts/events/project_process.md)."""

import uuid
from decimal import Decimal
from typing import Literal

from dexterhouse.apps.events.schemas.base import EventPayload
from dexterhouse.apps.events.schemas.common import ArtifactRef, PackageRef, _Strict

# project.*


class ProjectCreated(EventPayload):
    event_type = "project.created"
    actors = ("user",)

    name: str
    execution_mode: Literal["supervised", "autonomous"]
    budget: Decimal
    process: PackageRef


class ProjectStarted(EventPayload):
    event_type = "project.started"
    actors = ("user",)

    process_run_id: uuid.UUID


class ProjectWaiting(EventPayload):
    event_type = "project.waiting"

    reason: Literal["gate", "budget", "provider", "workspace"]
    gate_id: uuid.UUID | None = None


class ProjectResumed(EventPayload):
    event_type = "project.resumed"
    actors = ("user", "system")

    reason: str


class ProjectPaused(EventPayload):
    event_type = "project.paused"
    actors = ("user",)


class ProjectCompleted(EventPayload):
    event_type = "project.completed"

    duration_s: float
    cost: Decimal
    tasks_done: int
    iterations_total: int


class ProjectFailed(EventPayload):
    event_type = "project.failed"

    error_code: str
    phase_id: str | None = None


class ProjectRetried(EventPayload):
    event_type = "project.retried"
    actors = ("user",)

    from_phase_id: str


class ProjectArchived(EventPayload):
    event_type = "project.archived"
    actors = ("user",)


class ProjectBudgetChanged(EventPayload):
    event_type = "project.budget_changed"
    actors = ("user",)

    old: Decimal
    new: Decimal


# process.*


class ProcessPhase(_Strict):
    id: str
    needs: list[str]
    room: str


class ProcessStarted(EventPayload):
    event_type = "process.started"

    phases: list[ProcessPhase]


class _ProcessEnded(EventPayload):
    error_code: str | None = None


class ProcessCompleted(_ProcessEnded):
    event_type = "process.completed"


class ProcessFailed(_ProcessEnded):
    event_type = "process.failed"


class ProcessCancelled(_ProcessEnded):
    event_type = "process.cancelled"


# phase.*


class PhaseReady(EventPayload):
    event_type = "phase.ready"

    phase_id: str


class PhaseStarted(EventPayload):
    event_type = "phase.started"

    phase_id: str
    room: str
    agents: list[uuid.UUID]
    workspace_required: bool


class PhaseStepCompleted(EventPayload):
    event_type = "phase.step.completed"

    phase_id: str
    step: str
    agent_id: uuid.UUID
    artifacts: list[ArtifactRef]


class PhaseExitChecked(EventPayload):
    event_type = "phase.exit_checked"

    phase_id: str
    exit: str
    ok: bool
    attempt: int
    detail: str | None = None


class PhaseReopened(EventPayload):
    event_type = "phase.reopened"

    phase_id: str
    round: int
    comment: str


class PhaseCompleted(EventPayload):
    event_type = "phase.completed"

    phase_id: str
    duration_s: float
    cost: Decimal


class _PhaseEnded(EventPayload):
    phase_id: str
    error_code: str | None = None


class PhaseFailed(_PhaseEnded):
    event_type = "phase.failed"


class PhaseSkipped(_PhaseEnded):
    event_type = "phase.skipped"


# note.*


class NoteAdded(EventPayload):
    event_type = "note.added"
    actors = ("user",)

    note_id: uuid.UUID
    phase_run_id: uuid.UUID | None = None
    excerpt: str


class NoteConsumed(EventPayload):
    event_type = "note.consumed"
    actors = ("agent",)

    note_id: uuid.UUID
    agent_id: uuid.UUID
