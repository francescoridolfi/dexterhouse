# SPDX-License-Identifier: AGPL-3.0-or-later
"""`project.*` and `skills.read` (contracts/tools/memory.md): services and MCP server."""

import uuid

import pytest
from asgiref.sync import sync_to_async
from django.db import connections
from mcp import Client

from dexterhouse.apps.agents.models import AgentInstance
from dexterhouse.apps.agents.services import queue_turn
from dexterhouse.apps.events.models import Event
from dexterhouse.apps.projects.mcp_server import build_server, main
from dexterhouse.apps.projects.models import Note
from dexterhouse.apps.projects.services import tools
from dexterhouse.apps.projects.services.artifacts import save_artifact
from tests.workflows.conftest import drain

pytestmark = pytest.mark.django_db
LONG = "# Architecture\n\n## Modules\n" + "x" * (70 * 1024) + "\n## Data model\nBookings.\n"


@pytest.fixture
def ctx(started, settings, team_packages):
    """A completed autonomous project and a turn of its analyst."""

    def make(*, mode="supervised", may_ask=True, role="analyst") -> tools.ToolContext:
        settings.WORKFLOWS_FAKE_RUNNER = {"ask_questions": False, "tasks": 2}
        project = started(execution_mode="autonomous")
        drain(project)
        agent = AgentInstance.objects.get(project=project, role=role)
        turn = queue_turn(
            agent=agent,
            purpose="test",
            inputs={"mode": mode, "may_ask": may_ask},
            enqueue=False,
        )
        return tools.ToolContext(project_id=project.id, turn_id=turn.id)

    return make


def test_artifacts_lists_latest_versions_and_artifact_reads_them(ctx):
    context = ctx()
    project = context.turn().project
    save_artifact(project, kind="architecture", name="architecture.md", content=LONG)
    listed = {(a["kind"], a["name"]): a for a in tools.artifacts(context)["artifacts"]}
    assert listed[("architecture", "architecture.md")]["version"] == 2
    assert listed[("brief", "brief.md")]["produced_by"] == "user"
    assert listed[("stack", "stack.yaml")]["size"] is None
    assert [a["kind"] for a in tools.artifacts(context, "stack")["artifacts"]] == ["stack"]

    big = tools.artifact(context, "architecture")
    assert big["truncated"] is True
    assert big["sections"] == ["Modules", "Data model"]
    assert tools.artifact(context, "architecture", section="data model")["content"].startswith(
        "## Data model"
    )
    first = tools.artifact(context, "architecture", name="architecture.md", version=1)
    assert first["version"] == 1
    assert "content" in first
    assert tools.artifact(context, "stack")["data"]["language"] == "python"
    with pytest.raises(tools.ToolError, match="no section"):
        tools.artifact(context, "architecture", section="Nope")
    with pytest.raises(tools.ToolError, match="no release_notes artifact named x"):
        tools.artifact(context, "release_notes", name="x")


def test_tasks_and_notes(ctx, user):
    context = ctx()
    board = tools.tasks(context)["tasks"]
    assert [t["external_id"] for t in board] == ["T-01", "T-02"]
    assert board[1]["depends_on"] == ["T-01"]
    assert tools.tasks(context, status="pending")["tasks"] == []
    project = context.turn().project
    note = Note.objects.create(project=project, author=user, content="Use Tailwind")
    assert [n["content"] for n in tools.notes(context)["notes"]] == ["Use Tailwind"]
    note.refresh_from_db()
    assert note.consumed_by_turn_ids == [context.turn_id]
    assert tools.notes(context)["notes"] == []
    assert len(tools.notes(context, unconsumed_only=False)["notes"]) == 1


def test_ask_depends_on_mode_and_step(ctx):
    questions = [{"id": "q1", "text": "Payments?", "kind": "boolean"}]
    assert tools.ask(ctx(), questions)["mode"] == "ask"
    assert tools.ask(ctx(mode="autonomous"), questions)["mode"] == "assume"
    with pytest.raises(tools.ToolError, match="may not ask"):
        tools.ask(ctx(may_ask=False), questions)
    with pytest.raises(tools.ToolError, match="non-empty"):
        tools.ask(ctx(), [{"id": "q1"}])
    other = tools.ToolContext(project_id=uuid.uuid4(), turn_id=ctx().turn_id)
    with pytest.raises(tools.ToolError, match="unknown turn"):
        tools.ask(other, questions)


def test_read_skill_of_the_package_or_builtin(ctx, settings, tmp_path):
    context = ctx()
    skill = tools.read_skill(context, "brief-reading")
    assert "# Brief reading" in skill["content"]
    loaded = Event.objects.get(type="agent.skill.loaded")
    assert loaded.payload["skill"] == "brief-reading"
    with pytest.raises(tools.ToolError, match="not a file"):
        tools.read_skill(context, "brief-reading", path="../../agent.yaml")
    with pytest.raises(tools.ToolError, match="unknown skill"):
        tools.read_skill(context, "small-steps")  # the developer's, not the analyst's
    placeholder = ctx(role="tester")
    settings.BUILTIN_DIR = str(tmp_path)
    (tmp_path / "skills" / "shared").mkdir(parents=True)
    (tmp_path / "skills" / "shared" / "SKILL.md").write_text("# Shared\n")
    (tmp_path / "skills" / "shared" / "notes.md").write_text("More.\n")
    assert tools.read_skill(context, "shared", "notes.md")["content"] == "More.\n"
    AgentInstance.objects.filter(pk=placeholder.turn().agent_instance_id).update(
        package_path=str(tmp_path / "missing")
    )
    with pytest.raises(tools.ToolError, match="no package"):
        tools.read_skill(placeholder, "shared")


@pytest.fixture
def committed_ctx(ctx, monkeypatch) -> tools.ToolContext:
    """For transactional tests: steps are drained, never sent to Celery."""
    from dexterhouse.apps.workflows import tasks

    monkeypatch.setattr(tasks.run_step, "delay", lambda step_id: None)
    return ctx()


@pytest.mark.django_db(transaction=True)
async def test_mcp_server_groups(committed_ctx):
    context = committed_ctx
    async with Client(build_server(context.project_id, context.turn_id, "project")) as client:
        names = {t.name for t in (await client.list_tools()).tools}
        assert names == {
            "project_artifact",
            "project_artifacts",
            "project_tasks",
            "project_notes",
            "project_ask",
        }
        result = await client.call_tool("project_tasks", {})
        assert result.structured_content["tasks"][0]["external_id"] == "T-01"
        for name, args in (
            ("project_artifact", {"kind": "brief"}),
            ("project_artifacts", {}),
            ("project_notes", {}),
            ("project_ask", {"questions": [{"id": "q1", "text": "?"}]}),
        ):
            assert not (await client.call_tool(name, args)).is_error, name
    async with Client(build_server(context.project_id, context.turn_id, "skills")) as client:
        assert [t.name for t in (await client.list_tools()).tools] == ["skills_read"]
        result = await client.call_tool("skills_read", {"name": "brief-reading"})
        assert result.structured_content["name"] == "brief-reading"
    await sync_to_async(connections.close_all)()  # the tools ran in a worker thread


def test_main_needs_a_group_and_the_turn(monkeypatch, capsys):
    assert main(["nope"]) == 1
    monkeypatch.delenv("DH_TURN_ID", raising=False)
    monkeypatch.setenv("DH_PROJECT_ID", str(uuid.uuid4()))
    assert main(["skills"]) == 1
    assert "DH_TURN_ID" in capsys.readouterr().err
