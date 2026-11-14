# SPDX-License-Identifier: AGPL-3.0-or-later
"""The short map: size, how to query, entry points, modules, god nodes, communities.

Lines are added in that order while they fit `max_chars`, so a smaller budget keeps the
most useful part; the context builder gives it its `tree` budget.
"""

from collections import Counter, defaultdict
from typing import TYPE_CHECKING

from dexterhouse_runner.workspace_mcp.graph.build import is_test

if TYPE_CHECKING:
    from dexterhouse_runner.workspace_mcp.graph.query import GraphIndex

TOP = 10
HINT = (
    "Ask workspace.graph before reading: neighbors <node>, path <a> <b>, find <name>; "
    "then read only the files and lines you need."
)


def _where(index: "GraphIndex", nid: str) -> str:
    n = index.nodes[nid]
    if n["kind"] == "symbol":
        return f"{n['label']} ({n['path']}:{n['line']})"
    return str(n.get("path") or n["label"])


def _modules(index: "GraphIndex") -> list[str]:
    """Directories ranked by their own files (packages, not the folders that wrap them)."""
    files: Counter[str] = Counter()
    symbols: Counter[str] = Counter()
    for n in index.graph["nodes"]:
        if n["kind"] in ("file", "symbol") and n.get("path") and "/" in n["path"]:
            folder = n["path"].rsplit("/", 1)[0]
            (files if n["kind"] == "file" else symbols)[folder] += 1
    ranked = sorted(files, key=lambda m: (-files[m] - symbols[m] / 10, m))
    return [f"{m}/ ({files[m]} files, {symbols[m]} symbols)" for m in ranked[:TOP]]


def _communities(index: "GraphIndex", score: dict[str, int]) -> list[str]:
    groups: dict[int, list[str]] = defaultdict(list)
    for n in index.graph["nodes"]:
        if n["kind"] == "file" and n.get("community") is not None:
            groups[n["community"]].append(n["id"])
    lines = []
    for community in sorted(groups)[:6]:
        members = sorted(groups[community], key=lambda f: (-score.get(f, 0), f))
        names = ", ".join(index.nodes[f]["path"] for f in members[:4])
        more = " …" if len(members) > 4 else ""
        lines.append(f"- #{community} ({len(members)} files): {names}{more}")
    return lines


def render_summary(index: "GraphIndex", max_chars: int = 6000) -> str:
    graph = index.graph
    langs = Counter(n["lang"] for n in graph["nodes"] if n["kind"] == "file")
    stats = graph["stats"]
    head = (
        f"Code graph @{(graph.get('commit') or 'worktree')[:8]}: {stats['files']} files "
        f"({', '.join(f'{lang} {count}' for lang, count in langs.most_common())}), "
        f"{stats['symbols']} symbols, {stats['edges']} edges."
    )
    score = {nid: sum(index.degree(nid)) for nid in index.nodes}
    gods = sorted(
        (
            nid
            for nid, n in index.nodes.items()
            if n["kind"] in ("file", "symbol") and score[nid] and not is_test(str(n["path"]))
        ),
        key=lambda nid: (-score[nid], nid),
    )[:TOP]
    externals = sorted(
        (nid for nid, n in index.nodes.items() if n["kind"] == "external"),
        key=lambda nid: (-index.degree(nid)[0], nid),
    )[:TOP]
    sections: list[list[str]] = [
        [head],
        [HINT],
        ["Entry points: " + ", ".join(_where(index, e) for e in index.entry_points[:8])]
        if index.entry_points
        else [],
        ["Main modules:", *(f"- {m}" for m in _modules(index))],
        ["Most connected (in/out):"]
        + [f"- {_where(index, g)} {'/'.join(map(str, index.degree(g)))}" for g in gods],
        ["Communities:", *_communities(index, score)],
        [
            "External packages: "
            + ", ".join(f"{index.nodes[e]['label']} ({index.degree(e)[0]})" for e in externals)
        ]
        if externals
        else [],
    ]
    out: list[str] = []
    used = 0
    for section in sections:
        if len(section) == 1 and section[0].endswith(":"):
            continue
        for line in section:
            if used + len(line) + 1 > max_chars:
                return "\n".join(out)
            out.append(line)
            used += len(line) + 1
    return "\n".join(out)
