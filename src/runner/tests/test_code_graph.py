# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from pathlib import Path

from graph_fixture import FIXED, fixture_graph, write_project

from dexterhouse_runner.workspace_mcp.graph import build_graph, facts
from dexterhouse_runner.workspace_mcp.graph.lang_regex import go_facts, java_facts
from dexterhouse_runner.workspace_mcp.graph.resolve import Resolver

SHARED = Path(__file__).resolve().parents[2] / "schema/tests/fixtures/artifacts/code_graph.json"


def edges(graph: dict) -> set[tuple[str, str, str]]:
    return {(e["source"], e["kind"], e["target"]) for e in graph["edges"]}


def test_python_and_typescript_graph(repo: Path):
    graph = fixture_graph(repo)
    ids = {n["id"] for n in graph["nodes"]}
    assert graph["stats"] == {"files": 9, "symbols": 11, "edges": len(graph["edges"])}
    assert not any("node_modules" in i or ".venv" in i or "build/" in i for i in ids)
    found = edges(graph)
    assert {
        ("file:app/services.py", "imports", "file:app/models.py"),
        ("file:app/services.py", "imports", "ext:requests"),
        ("file:app/cli.py", "imports", "file:app/services.py"),
        ("sym:app/models.py::Course", "inherits", "sym:app/models.py::Base"),
        ("sym:app/models.py::Course", "defines", "sym:app/models.py::Course.save"),
        ("sym:app/models.py::Course.save", "calls", "sym:app/models.py::Base.validate"),
        ("sym:app/services.py::enroll", "calls", "sym:app/services.py::helper"),
        ("sym:tests/test_services.py::test_enroll", "calls", "sym:app/services.py::enroll"),
        ("file:tests/test_services.py", "tests", "file:app/services.py"),
        ("file:web/src/App.tsx", "imports", "file:web/src/api.ts"),
        ("file:web/src/App.tsx", "calls", "sym:web/src/api.ts::fetchCourses"),
        ("file:web/src/App.test.tsx", "tests", "file:web/src/App.tsx"),
        ("file:web/src/api.ts", "imports", "ext:axios"),
    } <= found
    assert not any(t.startswith("ext:os") for _, _, t in found)  # standard library
    node = {n["id"]: n for n in graph["nodes"]}
    assert node["sym:web/src/api.ts::Course"]["symbol_kind"] == "interface"
    assert node["sym:app/services.py::helper"]["line"] == 13
    assert node["file:app/models.py"]["parent"] == "module:app"
    assert node["file:app/models.py"]["community"] != node["file:web/src/api.ts"]["community"]


def test_the_shared_fixture_is_this_graph(repo: Path):
    """`code-app` reads the JSON fixture: it must stay what the extractor produces."""
    assert json.loads(SHARED.read_text("utf-8")) == fixture_graph(repo)


def test_graph_is_deterministic_and_incremental(repo: Path):
    write_project(repo)
    facts.clear_memory()
    first = build_graph(repo)
    assert first.parsed == 9
    assert build_graph(repo).parsed == 0
    assert (repo / facts.CACHE_FILE).is_file()
    facts.clear_memory()  # a restarted server reads the disk cache
    again = build_graph(repo)
    assert again.parsed == 0
    assert {**again.graph, **FIXED} == {**first.graph, **FIXED}
    (repo / "app/models.py").write_text("class Base:\n    pass\n", "utf-8")
    changed = build_graph(repo)
    assert changed.parsed == 1
    assert "sym:app/models.py::Course" not in {n["id"] for n in changed.graph["nodes"]}
    assert set(changed.entry_points) == {"file:app/cli.py", "file:web/src/main.ts"}


def test_go_and_java_facts():
    go = go_facts(
        'package main\n\nimport (\n\t"fmt"\n\tapi "example.com/shop/api"\n)\n\n'
        "type Store struct{}\n\nfunc (s *Store) Get(id int) {}\n\nfunc main() {}\n"
    )
    assert [i["spec"] for i in go["imports"]] == ["fmt", "example.com/shop/api"]
    assert go["symbols"] == [
        ["Store", "struct", 8],
        ["Store.Get", "method", 10],
        ["main", "function", 12],
    ]
    assert go["main"]
    java = java_facts(
        "import com.shop.model.Item;\nimport java.util.*;\n\n"
        "public final class Cart extends Base {\n  public static void main(String[] a) {}\n}\n"
    )
    assert java["imports"][1] == {"spec": "java.util", "binds": {}, "line": 2, "wildcard": True}
    assert java["symbols"] == [["Cart", "class", 4]]
    assert java["bases"] == [["Cart", "Base"]]
    resolver = Resolver({"api/h.go": "go", "com/shop/model/Item.java": "java"}, {"": "ex.com/s"})
    assert resolver.go("ex.com/s/api") == ("module", "api")
    assert resolver.go("fmt") is None
    assert resolver.java("com.shop.model.Item", False, "x.java") == (
        "file",
        "com/shop/model/Item.java",
    )
    assert resolver.java("org.lib.Thing", False, "x.java") == ("ext", "org.lib")
