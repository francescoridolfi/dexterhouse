# SPDX-License-Identifier: AGPL-3.0-or-later
import uuid
from types import SimpleNamespace

import pytest
from graph_fixture import write_project

from dexterhouse_runner.workspace_mcp import codegraph
from dexterhouse_runner.workspace_mcp.base import Config, ToolFailure
from dexterhouse_schema.runner import CodeGraph, WorkspaceCreate


@pytest.fixture
def project(cfg: Config) -> Config:
    write_project(cfg.root)
    return cfg


def test_summary_is_a_short_map(project: Config):
    result = codegraph.graph(project)
    text = result["summary"]
    assert result["stats"]["files"] == 9
    assert text.startswith("Code graph @")
    assert "Entry points: app/cli.py, web/src/main.ts" in text
    assert "- app/ (4 files, 6 symbols)" in text
    assert "requests (1)" in text.split("External packages: ")[1]
    assert "test_enroll" not in text.split("Communities:")[0]  # tests are not god nodes
    short = codegraph.graph(project, max_chars=500)["summary"]
    assert len(short) <= 500
    assert short.startswith("Code graph @")


def test_neighbors_path_and_find(project: Config):
    near = codegraph.graph(project, "neighbors", node="app/services.py")
    assert near["node"]["id"] == "file:app/services.py"
    assert {
        "edge": "imports",
        "id": "file:app/models.py",
        "kind": "file",
        "label": "models.py",
        "path": "app/models.py",
    } in near["out"]
    assert {i["id"] for i in near["in"]} >= {"file:app/cli.py", "file:tests/test_services.py"}
    module = codegraph.graph(project, "neighbors", node="app")
    assert len(module["children"]) == 4
    route = codegraph.graph(project, "path", node="test_enroll", target="Base.validate")
    assert route["found"]
    assert route["hops"][0]["from"].endswith("::test_enroll")
    assert route["hops"][-1]["to"] == "sym:app/models.py::Base.validate"
    found = codegraph.graph(project, "find", name="fetchCourses")["matches"][0]
    assert (found["path"], found["line"], found["symbol_kind"]) == ("web/src/api.ts", 7, "function")
    assert codegraph.graph(project, "find", name="zzz") == {"matches": [], "total": 0}


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"action": "explode"}, "invalid"),
        ({"action": "neighbors"}, "invalid"),
        ({"action": "path", "node": "app"}, "invalid"),
        ({"action": "neighbors", "node": "Course"}, "invalid"),  # a class and an interface
        ({"action": "neighbors", "node": "nowhere.py"}, "not_found"),
        ({"action": "find", "name": " "}, "invalid"),
    ],
)
def test_bad_queries(project: Config, kwargs: dict, code: str):
    with pytest.raises(ToolFailure) as exc:
        codegraph.graph(project, **kwargs)
    assert exc.value.code == code


def test_export_and_runner_system_call(runner: SimpleNamespace, stack: dict):
    ws = uuid.uuid4()
    runner.service.create(WorkspaceCreate(workspace_id=ws, project_id=uuid.uuid4(), stack=stack))
    write_project(runner.docker.root(ws))
    result = runner.service.code_graph(CodeGraph(workspace_id=ws, summary_chars=800))
    assert result.ok
    assert result.data["graph"]["schema"] == 1
    assert len(result.data["commit"]) == 40 == len(result.data["graph"]["commit"])
    assert len(result.data["summary"]) <= 800
    light = runner.service.code_graph(CodeGraph(workspace_id=ws, include_graph=False))
    assert "graph" not in light.data
    assert light.data["parsed"] == 0
    assert runner.pool.calls[-1] == (
        "workspace_graph_export",
        {"include_graph": False, "summary_chars": 6000},
    )
    missing = runner.service.code_graph(CodeGraph(workspace_id=uuid.uuid4()))
    assert missing.error.code == "workspace_not_ready"
