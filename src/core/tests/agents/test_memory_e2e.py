# SPDX-License-Identifier: AGPL-3.0-or-later
"""An indexed artifact is found by `memory.search` through the real stdio MCP server."""

import json
import uuid

import pytest
from django.db import connection

from dexterhouse.apps.agents.models import ToolCall
from dexterhouse.apps.agents.schemas import TaskInput, TurnInputs
from dexterhouse.apps.agents.services import queue_turn, run_turn
from dexterhouse.apps.gateway.providers.fake import FakeResponse
from dexterhouse.apps.memory.services.indexing import index_artifact

from .conftest import call, final

REQUIREMENTS = """# Requirements

## F-07 Waitlist

When a class is full, members join a FIFO waitlist and get an email when a seat frees up.

## F-08 Payments

No payments in 1.0.
"""


@pytest.mark.django_db(transaction=True)
def test_memory_search_over_mcp_finds_the_indexed_artifact(agent, script, monkeypatch):
    settings_dict = connection.settings_dict
    monkeypatch.setenv(
        "DATABASE_URL",
        f"postgres://{settings_dict['USER']}@{settings_dict['HOST']}:{settings_dict['PORT']}/{settings_dict['NAME']}",
    )
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "dexterhouse.settings.test")
    artifact = uuid.uuid4()
    index_artifact(
        organization_id=agent.organization_id,
        project_id=agent.project_id,
        artifact_id=artifact,
        version=1,
        kind="requirements",
        name="requirements.md",
        content=REQUIREMENTS,
    )
    script(
        FakeResponse(tool_calls=[call("memory.search", query="waitlist email FIFO", k=3)]),
        final(),
    )
    inputs = TurnInputs(
        task=TaskInput(title="Design the waitlist", acceptance=["FIFO order, email"])
    )
    turn = queue_turn(agent=agent, purpose="Architecture", inputs=inputs, enqueue=False)
    run_turn(turn.id)
    turn.refresh_from_db()

    # The context builder already put the most relevant chunk in the prompt...
    memory = turn.context_manifest["sections"]["memory"]
    assert memory[0]["artifact_id"] == str(artifact)
    assert "memory.search" in turn.context_manifest["tools"]
    # ...and the agent found it again through the MCP server during the turn.
    record = ToolCall.objects.get(agent_turn=turn)
    assert record.status == "done"
    result = json.loads(record.result["content"])
    assert result["hits"][0]["artifact"] == {
        "id": str(artifact),
        "kind": "requirements",
        "name": "requirements.md",
        "version": 1,
    }
    assert "FIFO waitlist" in result["hits"][0]["content"]
