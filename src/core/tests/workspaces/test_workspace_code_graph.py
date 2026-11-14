# SPDX-License-Identifier: AGPL-3.0-or-later
"""`code_graph` artifact after agent commits, and the graph summary for the context."""

import copy
import json
from pathlib import Path

import pytest

from dexterhouse.apps.agents.models import AgentInstance, AgentTurn
from dexterhouse.apps.agents.services.packages import load_tool_catalog
from dexterhouse.apps.projects.models import Artifact, ArtifactKind
from dexterhouse.apps.projects.services import artifacts as artifact_service
from dexterhouse.apps.workflows.runners.inputs import workspace_map
from dexterhouse.apps.workspaces import code_graph, services
from dexterhouse.apps.workspaces.tools import RunnerTools
from dexterhouse_schema.runner import ToolResult, WorkspaceChanged

FIXTURE = Path(__file__).resolve().parents[3] / "schema/tests/fixtures/artifacts/code_graph.json"
GRAPH = json.loads(FIXTURE.read_text("utf-8"))


def graph_at(commit: str) -> dict:
    return {**copy.deepcopy(GRAPH), "commit": commit}


@pytest.fixture
def live(project, runner_client):
    project.stack = {"language": "python", "workspace_image": "dexterhouse/workspace:python"}
    project.save(update_fields=["stack"])
    workspace = services.request(project)
    services.apply_changed(
        WorkspaceChanged(workspace_id=workspace.id, status="ready"), resume=False
    )
    return workspace


@pytest.fixture
def turn(project, organization):
    agent = AgentInstance.objects.create(
        organization=organization,
        project=project,
        role="developer",
        display_name="Developer",
        package_name="developer",
        package_version="0.1.0",
        package_path="",
        allowed_tools=["git.commit", "workspace.graph"],
    )
    return AgentTurn.objects.create(
        organization=organization, project=project, agent_instance=agent, purpose="test", inputs={}
    )


def commit(tools, runner_client, sha: str, seq: int, capture) -> None:
    runner_client.results["runner.tool.invoke"] = ToolResult(
        ok=True, data={"commit": sha, "branch": "task/T-01", "files_changed": 1, "message": "m"}
    )
    runner_client.results["runner.system.code_graph"] = ToolResult(
        ok=True, data={"graph": graph_at(sha), "summary": "Code graph @x", "parsed": 1}
    )
    with capture(execute=True):
        tools.call(load_tool_catalog().get("git.commit"), {"message": "feat: x"}, seq)


def test_each_new_commit_saves_a_code_graph_version(
    live, turn, project, runner_client, django_capture_on_commit_callbacks, monkeypatch
):
    indexed: list[str] = []
    monkeypatch.setattr(artifact_service, "index", lambda a: indexed.append(a.kind))
    tools = RunnerTools(turn)
    commit(tools, runner_client, "a" * 40, 1, django_capture_on_commit_callbacks)
    saved = Artifact.objects.get(project=project, kind=ArtifactKind.CODE_GRAPH)
    assert (saved.name, saved.version) == ("code_graph.json", 1)
    assert saved.data == graph_at("a" * 40)
    assert saved.produced_by_turn_id == turn.id
    assert saved.produced_by_role == "developer"
    export = next(m for t, m in runner_client.calls if t == "runner.system.code_graph")
    assert export.include_graph is True
    assert export.workspace_id == live.id
    commit(tools, runner_client, "a" * 40, 2, django_capture_on_commit_callbacks)  # same commit
    commit(tools, runner_client, "b" * 40, 3, django_capture_on_commit_callbacks)
    versions = Artifact.objects.filter(project=project, kind=ArtifactKind.CODE_GRAPH)
    assert sorted(versions.values_list("version", flat=True)) == [1, 2]
    assert "code_graph" not in indexed  # derived from the code: not in the project memory


def test_refresh_without_workspace_or_with_a_bad_graph(project, runner_client):
    assert code_graph.refresh(project.id) is None
    assert not runner_client.calls


def test_refresh_refuses_an_invalid_graph(live, project, runner_client):
    broken = {**graph_at("c" * 40), "stats": {"files": 0, "symbols": 0, "edges": 0}}
    runner_client.results["runner.system.code_graph"] = ToolResult(ok=True, data={"graph": broken})
    assert code_graph.refresh(project.id) is None
    runner_client.results["runner.system.code_graph"] = ToolResult.failure("timeout", "slow")
    assert code_graph.refresh(project.id) is None
    assert not Artifact.objects.filter(kind=ArtifactKind.CODE_GRAPH).exists()


def test_workspace_map_prefers_the_graph_summary(live, project, runner_client):
    runner_client.results["runner.system.code_graph"] = ToolResult(
        ok=True, data={"summary": "Code graph @abc: 9 files", "stats": {}}
    )
    assert workspace_map(project.id) == {
        "code_graph_summary": "Code graph @abc: 9 files",
        "workspace_tree": None,
    }
    assert runner_client.calls[-1][1].include_graph is False
    assert "runner.system.tree" not in runner_client.tasks()
    runner_client.results["runner.system.code_graph"] = ToolResult.failure("internal", "x")
    runner_client.results["runner.system.tree"] = ToolResult(ok=True, data={"tree": "app/"})
    assert workspace_map(project.id) == {"code_graph_summary": None, "workspace_tree": "app/"}
