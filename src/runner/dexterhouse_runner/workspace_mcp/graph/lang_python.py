# SPDX-License-Identifier: AGPL-3.0-or-later
"""Facts of one Python file from the standard library's `ast` (no code is executed).

Facts (JSON, cached by content hash): `symbols` [qualname, kind, line]; `imports`
{spec, level, names, binds, line}; `calls` [caller qualname or "", dotted callee];
`bases` [class qualname, dotted base]; `main` when the file runs as a script.
"""

import ast
from typing import Any

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


def _dotted(node: ast.expr) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        return ".".join([node.id, *reversed(parts)])
    return None


def _calls(caller: str, body: list[ast.stmt], out: list[list[str]]) -> None:
    seen: set[str] = set()
    for statement in body:
        for node in ast.walk(statement):
            if isinstance(node, ast.Call) and (name := _dotted(node.func)) and name not in seen:
                seen.add(name)
                out.append([caller, name])


def _is_main(node: ast.stmt) -> bool:
    if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
        return False
    left = node.test.left
    return isinstance(left, ast.Name) and left.id == "__name__"


def _imports(node: ast.Import | ast.ImportFrom) -> list[dict[str, Any]]:
    if isinstance(node, ast.Import):
        return [
            {
                "spec": alias.name,
                "level": 0,
                "names": [],
                # `import a.b` binds the dotted `a.b`, `import a.b as m` binds `m`
                "binds": {alias.asname or alias.name: ""},
                "line": node.lineno,
            }
            for alias in node.names
        ]
    names = [a.name for a in node.names if a.name != "*"]
    binds = {a.asname or a.name: a.name for a in node.names if a.name != "*"}
    return [
        {
            "spec": node.module or "",
            "level": node.level,
            "names": names,
            "binds": binds,
            "line": node.lineno,
        }
    ]


def _class(node: ast.ClassDef, prefix: str, facts: dict[str, Any]) -> None:
    qual = f"{prefix}{node.name}"
    facts["symbols"].append([qual, "class", node.lineno])
    facts["bases"] += [[qual, b] for base in node.bases if (b := _dotted(base))]
    for child in node.body:
        if isinstance(child, FunctionNode):
            facts["symbols"].append([f"{qual}.{child.name}", "method", child.lineno])
            _calls(f"{qual}.{child.name}", child.body, facts["calls"])
        elif isinstance(child, ast.ClassDef):
            _class(child, f"{qual}.", facts)


def python_facts(source: str) -> dict[str, Any]:
    facts: dict[str, Any] = {"symbols": [], "imports": [], "calls": [], "bases": [], "main": False}
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        facts["error"] = "syntax"
        return facts
    module_level: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, FunctionNode):
            facts["symbols"].append([node.name, "function", node.lineno])
            _calls(node.name, node.body, facts["calls"])
        elif isinstance(node, ast.ClassDef):
            _class(node, "", facts)
        else:
            module_level.append(node)
            facts["main"] = facts["main"] or _is_main(node)
    for node in ast.walk(tree):  # imports anywhere, also inside functions and `if`s
        if isinstance(node, ast.Import | ast.ImportFrom):
            facts["imports"] += _imports(node)
    _calls(
        "",
        [n for n in module_level if not isinstance(n, ast.Import | ast.ImportFrom)],
        facts["calls"],
    )
    return facts
