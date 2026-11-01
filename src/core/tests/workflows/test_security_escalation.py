# SPDX-License-Identifier: AGPL-3.0-or-later
"""T4 / ST-08: the third refused tool call blocks the turn and escalates to a human."""

import pytest

from dexterhouse.apps.agents.models import AgentInstance
from dexterhouse.apps.agents.services.packages import ToolCatalog
from dexterhouse.apps.agents.services.tool_gateway import (
    MAX_DENIALS,
    PermissionLimitError,
    ToolGateway,
)
from dexterhouse.apps.agents.services.turns import queue_turn
from dexterhouse.apps.gateway.messages import ToolCallPart
from dexterhouse.apps.workflows import services
from dexterhouse.apps.workflows.models import Gate
from tests.workflows.conftest import drain

pytestmark = pytest.mark.django_db


def test_blocked_turn_opens_a_security_escalation(started, user):
    project = started()
    agent = AgentInstance.objects.filter(project=project).first()
    turn = queue_turn(agent=agent, purpose="analysis", inputs={}, enqueue=False)
    gateway = ToolGateway(turn, None, ToolCatalog({}), frozenset())
    for seq in range(1, MAX_DENIALS):
        assert gateway.invoke(seq, ToolCallPart(id=f"c{seq}", name="git.push", args={})).is_error
    assert not Gate.objects.filter(project=project, type="escalation").exists()
    with pytest.raises(PermissionLimitError):
        gateway.invoke(MAX_DENIALS, ToolCallPart(id="c3", name="git.push", args={}))
    gate = Gate.objects.get(project=project, type="escalation", status="open")
    assert gate.payload["reason"] == "security"
    assert gate.payload["details"]["tool"] == "git.push"
    assert gate.payload["details"]["violations"] == MAX_DENIALS
    project.refresh_from_db()
    assert project.status == "waiting"
    assert services.decide(gate.id, user, decision="accept")[1] == "phase_resumed"
    drain(project)


def test_blocked_turn_outside_a_process_is_only_blocked(project, organization):
    agent = AgentInstance.objects.create(
        organization=organization,
        project=project,
        role="developer",
        display_name="Developer",
        package_name="developer",
        package_version="0.1.0",
        package_path="",
        allowed_tools=[],
    )
    turn = queue_turn(agent=agent, purpose="test", inputs={}, enqueue=False)
    gateway = ToolGateway(turn, None, ToolCatalog({}), frozenset())
    for seq in range(1, MAX_DENIALS):
        gateway.invoke(seq, ToolCallPart(id=f"c{seq}", name="git.push", args={}))
    with pytest.raises(PermissionLimitError):
        gateway.invoke(MAX_DENIALS, ToolCallPart(id="last", name="git.push", args={}))
    assert not Gate.objects.filter(project=project).exists()
