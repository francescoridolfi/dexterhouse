# SPDX-License-Identifier: AGPL-3.0-or-later
"""The combined built-in MCP server: one process per turn for every built-in worker tool."""

import json
import uuid

import pytest
from asgiref.sync import sync_to_async
from django.db import connections
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
    "marketplace_search",
    "marketplace_details",
    "packages_installed",
    "packages_propose",
    "packages_install",
}


async def test_combined_server_exposes_every_builtin_tool():
    async with Client(build_server(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())) as client:
        names = {t.name for t in (await client.list_tools()).tools}
    assert names == EXPECTED_TOOLS


async def test_marketplace_search_answers_unreachable_without_a_registry():
    async with Client(build_server(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())) as client:
        result = await client.call_tool("marketplace_search", {"query": "frontend"})
    data = json.loads(result.content[0].text)
    assert (data["source"], data["results"]) == ("unreachable", [])


def test_main_requires_the_project_organization_and_turn(monkeypatch, capsys):
    for name in ("DH_PROJECT_ID", "DH_ORGANIZATION_ID", "DH_TURN_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DH_PROJECT_ID", str(uuid.uuid4()))
    assert main() == 1
    assert "DH_TURN_ID" in capsys.readouterr().err


@pytest.mark.django_db
async def test_package_tools_answer_through_mcp():
    async with Client(build_server(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())) as client:
        installed = await client.call_tool("packages_installed", {"kind": "tool"})
        names = {p["name"] for p in json.loads(installed.content[0].text)["packages"]}
        proposed = await client.call_tool(
            "packages_propose", {"proposals": [{"name": "ghost-agent", "for_tasks": ["T-01"]}]}
        )
        install = await client.call_tool("packages_install", {"name": "ghost-agent"})
        details = await client.call_tool("marketplace_details", {"name": "ghost-agent"})
    await sync_to_async(connections.close_all)()  # the tools' thread: no connection left open
    assert {"marketplace", "packages"} <= names  # the built-ins are global
    assert json.loads(proposed.content[0].text)["rejected"][0]["name"] == "ghost-agent"
    assert install.is_error
    assert "unknown project" in install.content[0].text
    assert details.is_error
    assert "no registry configured" in details.content[0].text
