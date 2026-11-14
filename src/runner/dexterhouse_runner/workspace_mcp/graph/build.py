# SPDX-License-Identifier: AGPL-3.0-or-later
"""Facts -> the `code_graph` artifact (schema 1, see `dexterhouse_schema.artifacts.code_graph`).

Node ids: `file:<path>`, `module:<dir>`, `sym:<path>::<qualname>`, `ext:<package>`.
Edges: `imports` (file -> file | module | external), `defines` (file -> symbol, class ->
method), `calls` and `inherits` (symbol or file -> symbol), `tests` (test file -> the
files it imports). Everything is sorted, so the same tree gives the same graph.
"""

import posixpath
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dexterhouse_runner.workspace_mcp.graph.communities import communities
from dexterhouse_runner.workspace_mcp.graph.facts import collect
from dexterhouse_runner.workspace_mcp.graph.link import link_file
from dexterhouse_runner.workspace_mcp.graph.resolve import Resolver
from dexterhouse_runner.workspace_mcp.graph.scan import source_files

_TEST_FILE = re.compile(
    r"(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]*\.py$|_test\.(py|go)$|\.(test|spec)\.[jt]sx?$"
    r"|Tests?\.java$"
)
_ENTRY_NAMES = frozenset(
    "manage.py __main__.py main.py app.py wsgi.py asgi.py cli.py server.py main.ts main.tsx "
    "index.ts index.tsx index.js main.js server.ts server.js main.go".split()
)


@dataclass
class Built:
    graph: dict[str, Any]
    entry_points: list[str] = field(default_factory=list)
    tests: set[str] = field(default_factory=set)
    parsed: int = 0


def is_test(path: str) -> bool:
    return bool(_TEST_FILE.search(path))


def node(nid: str, kind: str, label: str, **extra: Any) -> dict[str, Any]:
    base = {"path": None, "lang": None, "line": None, "symbol_kind": None, "parent": None}
    return {"id": nid, "kind": kind, "label": label, **base, **extra, "community": None}


def _go_modules(root: Path, paths: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for folder in sorted({posixpath.dirname(p) for p in paths if p.endswith(".go")} | {""}):
        try:
            text = (root / folder / "go.mod").read_text("utf-8")
        except OSError:
            continue
        if match := re.search(r"^module\s+(\S+)", text, re.MULTILINE):
            out[folder] = match.group(1)
    return out


def _modules(paths: list[str]) -> dict[str, dict[str, Any]]:
    dirs: set[str] = set()
    for path in paths:
        folder = posixpath.dirname(path)
        while folder:
            dirs.add(folder)
            folder = posixpath.dirname(folder)
    out = {}
    for folder in sorted(dirs):
        parent = posixpath.dirname(folder)
        out[folder] = node(
            f"module:{folder}",
            "module",
            folder,
            path=folder,
            parent=f"module:{parent}" if parent else None,
        )
    return out


def build_graph(root: Path, commit: str = "") -> Built:
    root = root.resolve()
    files = source_files(root)
    facts, parsed = collect(root, files)
    langs = {p: lang for p, lang in files if p in facts}
    resolver = Resolver(langs, _go_modules(root, list(langs)))
    nodes: dict[str, dict[str, Any]] = {f"module:{d}": n for d, n in _modules(list(langs)).items()}
    edges: set[tuple[str, str, str]] = set()
    symbols: dict[str, dict[str, str]] = {}
    for path, lang in langs.items():
        folder = posixpath.dirname(path)
        nodes[f"file:{path}"] = node(
            f"file:{path}",
            "file",
            posixpath.basename(path),
            path=path,
            lang=lang,
            parent=f"module:{folder}" if folder else None,
        )
        symbols[path] = {}
        for qual, kind, line in facts[path]["symbols"]:
            sid = f"sym:{path}::{qual}"
            owner = qual.rsplit(".", 1)[0] if "." in qual else ""
            parent = symbols[path].get(owner, f"file:{path}")
            symbols[path][qual] = sid
            nodes[sid] = node(
                sid,
                "symbol",
                qual,
                path=path,
                lang=lang,
                line=line,
                symbol_kind=kind,
                parent=parent,
            )
            edges.add((parent, sid, "defines"))
    tests = {p for p in langs if is_test(p)}
    for path, lang in langs.items():
        for source, target, kind in link_file(path, lang, facts[path], resolver, symbols):
            if target.startswith("ext:") and target not in nodes:
                nodes[target] = node(target, "external", target[4:])
            if target in nodes and source in nodes and source != target:
                edges.add((source, target, kind))
    for source, target, kind in list(edges):
        if kind == "imports" and source[5:] in tests and target.startswith("file:"):
            if target[5:] not in tests:
                edges.add((source, target, "tests"))
    for nid, community in communities(nodes, edges).items():
        nodes[nid]["community"] = community
    entry = sorted(
        f"file:{p}"
        for p in langs
        if p not in tests and (facts[p].get("main") or posixpath.basename(p) in _ENTRY_NAMES)
    )
    ordered = sorted(edges, key=lambda e: (e[0], e[2], e[1]))
    graph = {
        "schema": 1,
        "commit": commit,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "stats": {
            "files": len(langs),
            "symbols": sum(len(s) for s in symbols.values()),
            "edges": len(ordered),
        },
        "nodes": [nodes[k] for k in sorted(nodes)],
        "edges": [{"source": s, "target": t, "kind": k} for s, t, k in ordered],
    }
    return Built(graph=graph, entry_points=entry, tests=tests, parsed=parsed)
