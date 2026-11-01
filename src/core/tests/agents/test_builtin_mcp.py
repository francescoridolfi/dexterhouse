# SPDX-License-Identifier: AGPL-3.0-or-later
"""The combined built-in MCP server: one process per turn for memory, project and skills."""

import uuid

from mcp import Client

from dexterhouse.apps.agents.builtin_mcp import build_server, main

EXPECTED_TOOLS = {
    "memory_search",
    "memory_recent",
    "project_artifact",
    "project_artifacts",
    "project_tasks",
    "project_notes",
    "project_ask",
    "skills_read",
}


async def test_combined_server_exposes_every_builtin_tool():
    async with Client(build_server(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())) as client:
        names = {t.name for t in (await client.list_tools()).tools}
    assert names == EXPECTED_TOOLS


def test_main_requires_the_project_organization_and_turn(monkeypatch, capsys):
    for name in ("DH_PROJECT_ID", "DH_ORGANIZATION_ID", "DH_TURN_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DH_PROJECT_ID", str(uuid.uuid4()))
    assert main() == 1
    assert "DH_TURN_ID" in capsys.readouterr().err
