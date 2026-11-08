# SPDX-License-Identifier: AGPL-3.0-or-later
"""The module-level imports of the core form no cycle.

The engine, the workspaces and the agents call each other back (a ready workspace resumes
the engine, an escalation retries a workspace, a step is queued by name): those calls go
through imports inside functions on purpose. Moving one of them to the top of its file
would import fine in one process order and crash in another, so this test parses every
module of the package and checks the graph of its top-level imports with no Django and no
import at all.
"""

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "dexterhouse"
ROOT = "dexterhouse"


def _modules() -> dict[str, Path]:
    found: dict[str, Path] = {}
    for path in PACKAGE.rglob("*.py"):
        if "migrations" in path.parts:
            continue
        rel = path.relative_to(PACKAGE.parent).with_suffix("")
        parts = list(rel.parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        found[".".join(parts)] = path
    return found


def _walk_skipping_defs(tree: ast.Module):
    """Yield module-level statements, descending into blocks but never into definitions."""
    stack = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        yield node
        stack.extend(ast.iter_child_nodes(node))


def _graph() -> dict[str, set[str]]:
    modules = _modules()
    known = set(modules)
    graph: dict[str, set[str]] = {}
    for module, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        targets: set[str] = set()
        for stmt in _walk_skipping_defs(tree):
            if isinstance(stmt, ast.Import):
                targets.update(a.name for a in stmt.names if a.name.startswith(ROOT))
            elif isinstance(stmt, ast.ImportFrom) and stmt.module:
                base = stmt.module
                if stmt.level:
                    base = f"{module.rsplit('.', stmt.level)[0]}.{stmt.module}"
                if base.startswith(ROOT):
                    for alias in stmt.names:
                        sub = f"{base}.{alias.name}"
                        targets.add(sub if sub in known else base)
        graph[module] = {t for t in targets if t in known and t != module}
    return graph


def _find_cycle(graph: dict[str, set[str]]) -> list[str] | None:
    state: dict[str, int] = {}
    path: list[str] = []

    def visit(node: str) -> list[str] | None:
        state[node] = 1
        path.append(node)
        for nxt in sorted(graph.get(node, ())):
            if state.get(nxt) == 1:
                return [*path[path.index(nxt) :], nxt]
            if nxt not in state:
                found = visit(nxt)
                if found:
                    return found
        path.pop()
        state[node] = 2
        return None

    for start in sorted(graph):
        if start not in state:
            found = visit(start)
            if found:
                return found
    return None


def test_no_module_level_import_cycle():
    graph = _graph()
    assert len(graph) > 100, "the package walk found too few modules"
    cycle = _find_cycle(graph)
    assert cycle is None, "module-level import cycle: " + " -> ".join(cycle)


def test_the_callbacks_stay_lazy():
    """The known callbacks are imported inside functions, never at module level."""
    graph = _graph()
    apps = "dexterhouse.apps"
    for importer, imported in (
        (f"{apps}.workflows.engine.common", f"{apps}.workflows.tasks"),
        (f"{apps}.workspaces.client", f"{apps}.workspaces.services"),
        (f"{apps}.workspaces.services", f"{apps}.workflows.engine.common"),
        (f"{apps}.workspaces.services", f"{apps}.workflows.escalations"),
        (f"{apps}.workflows.escalations", f"{apps}.workflows.engine.loop"),
    ):
        assert imported not in graph[importer], f"{importer} imports {imported} at module level"
