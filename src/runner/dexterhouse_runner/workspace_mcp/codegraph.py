# SPDX-License-Identifier: AGPL-3.0-or-later
"""`workspace.graph` (agents) and `workspace_graph_export` (system, not a permission).

Every call rebuilds the graph from the working tree; unchanged files come from the facts
cache, so the cost is one read and one hash per file. The export is what the core saves
as the `code_graph` artifact after a commit and what fills the `tree` context section.
"""

from typing import Any, Literal

from dexterhouse_runner.workspace_mcp import gitops
from dexterhouse_runner.workspace_mcp.base import Config, ToolFailure, clip
from dexterhouse_runner.workspace_mcp.graph import GraphIndex, build_graph
from dexterhouse_runner.workspace_mcp.graph.build import Built

Action = Literal["summary", "neighbors", "path", "find"]
MAX_LIMIT = 100


def _head(cfg: Config) -> str:
    try:
        return gitops.git(cfg, "rev-parse", "--verify", "-q", "HEAD", check=False).strip()
    except ToolFailure:
        return ""


def _build(cfg: Config) -> Built:
    if not cfg.root.is_dir():
        raise ToolFailure("workspace_not_ready", "the workspace root does not exist")
    return build_graph(cfg.root, _head(cfg))


def graph(
    cfg: Config,
    action: str = "summary",
    node: str | None = None,
    target: str | None = None,
    name: str | None = None,
    limit: int = 30,
    max_chars: int = 6000,
) -> dict[str, Any]:
    limit = max(1, min(int(limit), MAX_LIMIT))
    if action not in ("summary", "neighbors", "path", "find"):
        raise ToolFailure("invalid", "action must be summary, neighbors, path or find")
    if action in ("neighbors", "path") and not node:
        raise ToolFailure("invalid", f"{action} needs `node`")
    if action == "path" and not target:
        raise ToolFailure("invalid", "path needs `node` and `target`")
    built = _build(cfg)
    index = GraphIndex(built.graph, built.entry_points)
    if action == "summary":
        text, _ = clip(index.summary(max(500, min(int(max_chars), 60_000))))
        return {"commit": built.graph["commit"], "stats": built.graph["stats"], "summary": text}
    if action == "neighbors":
        return index.neighbors(str(node), limit)
    if action == "path":
        return index.path(str(node), str(target))
    return index.find(str(name or node or ""), limit)


def export(cfg: Config, include_graph: bool = True, summary_chars: int = 6000) -> dict[str, Any]:
    built = _build(cfg)
    summary = GraphIndex(built.graph, built.entry_points).summary(summary_chars)
    result: dict[str, Any] = {
        "summary": summary,
        "parsed": built.parsed,
        "stats": built.graph["stats"],
        "commit": built.graph["commit"],
    }
    if include_graph:
        result["graph"] = built.graph
    return result
