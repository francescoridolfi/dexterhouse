# SPDX-License-Identifier: AGPL-3.0-or-later
"""agent.* payloads (contracts/events/agents.md)."""

import uuid
from decimal import Decimal
from typing import Literal

from pydantic import Field

from dexterhouse.apps.events.schemas.base import EventPayload
from dexterhouse.apps.events.schemas.common import ArtifactRef, PackageRef, _Strict


class Avatar(_Strict):
    model: str
    color: str


class AgentHired(EventPayload):
    event_type = "agent.hired"

    agent_id: uuid.UUID
    role: str
    display_name: str
    package: PackageRef
    source: Literal["builtin", "marketplace", "local"]
    room: str
    avatar: Avatar
    allowed_tools: list[str]


class AgentReleased(EventPayload):
    event_type = "agent.released"
    actors = ("user", "system")

    agent_id: uuid.UUID
    reason: str


class AgentMoved(EventPayload):
    event_type = "agent.moved"

    agent_id: uuid.UUID
    from_room: str
    to_room: str
    reason: Literal["turn", "idle", "blocked"]


class AgentStatus(EventPayload):
    event_type = "agent.status"

    agent_id: uuid.UUID
    status: Literal["idle", "working", "blocked"]


class AgentTurnQueued(EventPayload):
    event_type = "agent.turn.queued"

    turn_id: uuid.UUID
    agent_id: uuid.UUID
    purpose: str
    task_id: uuid.UUID | None = None
    step: str | None = None


class TurnContext(_Strict):
    """What went into the prompt, as counts (the full manifest is on `AgentTurn`)."""

    artifacts: int
    memory_chunks: int
    notes: int
    skills: list[str]
    input_tokens_est: int


class AgentTurnStarted(EventPayload):
    event_type = "agent.turn.started"
    actors = ("agent",)

    turn_id: uuid.UUID
    agent_id: uuid.UUID
    room: str
    purpose: str
    context: TurnContext


class AgentSpeaking(EventPayload):
    """Streamed text chunk: Redis only, never written to `Event`."""

    event_type = "agent.speaking"
    persisted = False
    actors = ("agent",)

    turn_id: uuid.UUID
    agent_id: uuid.UUID
    text: str
    seq: int


class AgentSkillLoaded(EventPayload):
    event_type = "agent.skill.loaded"
    actors = ("agent",)

    turn_id: uuid.UUID
    agent_id: uuid.UUID
    skill: str


class AgentToolRequested(EventPayload):
    event_type = "agent.tool.requested"
    actors = ("agent",)

    turn_id: uuid.UUID
    tool: str
    call_seq: int


class AgentToolUsed(EventPayload):
    event_type = "agent.tool.used"
    actors = ("agent",)

    turn_id: uuid.UUID
    tool: str
    call_seq: int
    allowed: bool
    duration_ms: float
    result_excerpt: str = Field(max_length=500)
    denied_reason: str | None = None


class AgentTurnCompleted(EventPayload):
    event_type = "agent.turn.completed"
    actors = ("agent",)

    turn_id: uuid.UUID
    agent_id: uuid.UUID
    duration_s: float
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    cost: Decimal
    tool_calls: int
    artifacts: list[ArtifactRef]


class AgentTurnFailed(EventPayload):
    event_type = "agent.turn.failed"
    actors = ("agent",)

    turn_id: uuid.UUID
    agent_id: uuid.UUID
    error_code: str
    attempt: int
    will_retry: bool


class AgentTurnCancelled(EventPayload):
    event_type = "agent.turn.cancelled"

    turn_id: uuid.UUID
    reason: str


class Question(_Strict):
    id: str
    text: str
    kind: Literal["text", "choice"]
    options: list[str] | None = None


class AgentQuestionAsked(EventPayload):
    event_type = "agent.question.asked"
    actors = ("agent",)

    turn_id: uuid.UUID
    gate_id: uuid.UUID
    questions: list[Question]
