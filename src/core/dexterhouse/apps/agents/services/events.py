# SPDX-License-Identifier: AGPL-3.0-or-later
"""`agent.*` and `security.*` emission for a turn, plus the throttled `agent.speaking`."""

import time
from typing import Any

from dexterhouse.apps.agents.models import AgentTurn
from dexterhouse.apps.events.schemas import Actor
from dexterhouse.apps.events.services.publisher import emit

SPEAKING_INTERVAL_S = 0.5  # at most 2 per second per agent
SPEAKING_CHARS = 280
SYSTEM = Actor(type="system", name="agents")


def agent_actor(turn: AgentTurn) -> Actor:
    agent = turn.agent_instance
    return Actor(type="agent", id=agent.id, name=agent.display_name)


def emit_turn(
    turn: AgentTurn, event_type: str, payload: dict[str, Any], *, system: bool = False
) -> None:
    emit(
        event_type,
        organization_id=turn.organization_id,
        project_id=turn.project_id,
        actor=SYSTEM if system else agent_actor(turn),
        payload=payload,
        correlation_id=turn.id,
    )


class Speaker:
    """Collects `TextDelta`s and publishes the last 280 characters at most twice a second."""

    def __init__(self, turn: AgentTurn, clock: Any = time.monotonic) -> None:
        self.turn = turn
        self.clock = clock
        self.buffer = ""
        self.seq = 0
        self.last = float("-inf")

    def __call__(self, event: Any) -> None:
        if getattr(event, "kind", None) != "text_delta":
            return
        self.buffer = (self.buffer + event.text)[-SPEAKING_CHARS:]
        now = self.clock()
        if now - self.last >= SPEAKING_INTERVAL_S:
            self.flush(now)

    def flush(self, now: float | None = None) -> None:
        if not self.buffer.strip():
            return
        self.seq += 1
        self.last = self.clock() if now is None else now
        emit_turn(
            self.turn,
            "agent.speaking",
            {
                "turn_id": str(self.turn.id),
                "agent_id": str(self.turn.agent_instance_id),
                "text": self.buffer,
                "seq": self.seq,
            },
        )
