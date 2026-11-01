# SPDX-License-Identifier: AGPL-3.0-or-later
"""`risk: high` tools need a human (F-004): the gateway refuses the call and escalates."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from dexterhouse.apps.agents.models import ToolCall
from dexterhouse.apps.agents.services import tool_gateway
from dexterhouse.apps.agents.services.packages import ToolCatalog
from dexterhouse.apps.agents.services.tool_gateway import NEEDS_HUMAN, ToolGateway
from dexterhouse.apps.agents.services.turns import queue_turn
from dexterhouse.apps.events.models import Event
from dexterhouse.apps.gateway.messages import ToolCallPart

pytestmark = pytest.mark.django_db


def binding(risk: str) -> SimpleNamespace:
    return SimpleNamespace(
        permission=SimpleNamespace(risk=risk, args_policy=None, mcp_tool="exec"),
        tool=SimpleNamespace(runs_in="worker"),
        root=Path("/nonexistent"),
    )


class Pool:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def call(self, _binding, args):
        self.calls.append(args)
        return SimpleNamespace(content="ok", is_error=False)


@pytest.fixture
def turn(agent):
    return queue_turn(agent=agent, purpose="analysis", inputs={}, enqueue=False)


def gateway(turn, risk: str, pool: Pool) -> ToolGateway:
    catalog = ToolCatalog({"workspace.exec": binding(risk)})
    return ToolGateway(turn, pool, catalog, frozenset({"workspace.exec"}))


def test_high_risk_call_is_refused_and_escalated(turn, monkeypatch):
    requested = []
    monkeypatch.setattr(
        "dexterhouse.apps.workflows.escalations.escalate",
        lambda project, reason, payload: requested.append((project, reason, payload)),
    )
    pool = Pool()
    part = gateway(turn, "high", pool).invoke(
        1, ToolCallPart(id="c1", name="workspace.exec", args={"cmd": "rm -rf build", "token": "x"})
    )
    assert part.is_error
    assert "high-risk" in str(part.content)
    assert pool.calls == []
    record = ToolCall.objects.get(agent_turn=turn)
    assert (record.allowed, record.denied_reason) == (False, NEEDS_HUMAN)
    turn.refresh_from_db()
    assert turn.denied_count == 0  # not a security violation
    project_id, reason, details = requested[0]
    assert (project_id, reason, details["tool"]) == (
        turn.project_id,
        "tool_high_risk",
        "workspace.exec",
    )
    assert details["args"]["token"] != "x"  # redacted
    used = Event.objects.get(type="agent.tool.used")
    assert used.payload["denied_reason"] == NEEDS_HUMAN
    # A resumed turn gets the recorded refusal, not a second escalation.
    again = gateway(turn, "high", pool).invoke(
        1, ToolCallPart(id="c1", name="workspace.exec", args={})
    )
    assert again.is_error
    assert len(requested) == 1


def test_high_risk_without_a_running_process_is_only_refused(turn):
    part = gateway(turn, "high", Pool()).invoke(
        1, ToolCallPart(id="c1", name="workspace.exec", args={})
    )
    assert part.is_error  # draft project: the escalation is logged and skipped


def test_approved_or_lower_risk_tools_run(turn, monkeypatch):
    pool = Pool()
    assert (
        not gateway(turn, "medium", pool)
        .invoke(1, ToolCallPart(id="c1", name="workspace.exec", args={}))
        .is_error
    )
    monkeypatch.setattr(tool_gateway, "_human_approved", lambda turn, tool: True)
    assert (
        not gateway(turn, "high", pool)
        .invoke(2, ToolCallPart(id="c2", name="workspace.exec", args={}))
        .is_error
    )
    assert len(pool.calls) == 2
