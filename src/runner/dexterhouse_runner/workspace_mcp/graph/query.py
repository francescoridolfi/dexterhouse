# SPDX-License-Identifier: AGPL-3.0-or-later
"""Compact answers over a built graph: `summary`, `neighbors`, `path`, `find`.

Node arguments accept an id (`file:a.py`, `sym:a.py::C.m`), a path (`a.py`), `path::Qual`
or a bare symbol name (ambiguous names answer `invalid` with the candidates).
"""

from collections import Counter, defaultdict, deque
from typing import Any

from dexterhouse_runner.workspace_mcp.base import ToolFailure
from dexterhouse_runner.workspace_mcp.graph.summary import render_summary

MAX_PATH_HOPS = 8


def brief(n: dict[str, Any]) -> dict[str, Any]:
    out = {"id": n["id"], "kind": n["kind"], "label": n["label"]}
    out |= {k: n[k] for k in ("path", "line", "symbol_kind") if n.get(k) is not None}
    return out


class GraphIndex:
    def __init__(self, graph: dict[str, Any], entry_points: list[str] | None = None) -> None:
        self.graph = graph
        self.nodes = {n["id"]: n for n in graph["nodes"]}
        self.entry_points = entry_points or []
        self.out: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self.inc: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for e in graph["edges"]:
            self.out[e["source"]].append((e["kind"], e["target"]))
            self.inc[e["target"]].append((e["kind"], e["source"]))
        self.children: dict[str, list[str]] = defaultdict(list)
        self.by_name: dict[str, list[str]] = defaultdict(list)
        for n in graph["nodes"]:
            if n["kind"] in ("file", "module") and n.get("parent"):
                self.children[n["parent"]].append(n["id"])
            if n["kind"] == "symbol":
                self.by_name[n["label"].rsplit(".", 1)[-1].lower()].append(n["id"])
                self.by_name[n["label"].lower()].append(n["id"])

    def degree(self, nid: str) -> tuple[int, int]:
        def count(edges: list[tuple[str, str]]) -> int:
            return sum(1 for kind, _ in edges if kind != "defines")

        return count(self.inc.get(nid, [])), count(self.out.get(nid, []))

    def lookup(self, ref: str) -> str:
        ref = (ref or "").strip()
        for candidate in (
            ref,
            f"file:{ref}",
            f"module:{ref.rstrip('/')}",
            f"sym:{ref}",
            f"ext:{ref}",
        ):
            if candidate in self.nodes:
                return candidate
        matches = sorted(dict.fromkeys(self.by_name.get(ref.lower(), [])))
        if len(matches) == 1:
            return matches[0]
        if matches:
            raise ToolFailure("invalid", f"{ref!r} is ambiguous", candidates=matches[:20])
        raise ToolFailure("not_found", f"{ref!r}: no such node; try action=find")

    def summary(self, max_chars: int = 6000) -> str:
        return render_summary(self, max_chars)

    def _listing(self, edges: list[tuple[str, str]], limit: int) -> list[dict[str, Any]]:
        return [{"edge": kind, **brief(self.nodes[other])} for kind, other in edges[:limit]]

    def neighbors(self, ref: str, limit: int = 40) -> dict[str, Any]:
        nid = self.lookup(ref)
        out, inc = self.out.get(nid, []), self.inc.get(nid, [])
        result: dict[str, Any] = {
            "node": brief(self.nodes[nid]),
            "out": self._listing(out, limit),
            "in": self._listing(inc, limit),
        }
        if self.children.get(nid):
            result["children"] = [brief(self.nodes[c]) for c in self.children[nid][:limit]]
        if len(out) > limit or len(inc) > limit:
            result["truncated"] = True
        return result

    def path(self, source: str, target: str) -> dict[str, Any]:
        start, goal = self.lookup(source), self.lookup(target)
        previous: dict[str, tuple[str, str, str] | None] = {start: None}
        queue = deque([(start, 0)])
        while queue:
            current, hops = queue.popleft()
            if current == goal:
                break
            if hops >= MAX_PATH_HOPS:
                continue
            steps = [(k, o, "->") for k, o in self.out.get(current, [])]
            steps += [(k, o, "<-") for k, o in self.inc.get(current, [])]
            for kind, other, direction in sorted(steps, key=lambda s: (s[1], s[0])):
                if other not in previous:
                    previous[other] = (current, kind, direction)
                    queue.append((other, hops + 1))
        if goal not in previous:
            return {"found": False, "from": start, "to": goal, "max_hops": MAX_PATH_HOPS}
        hops_out: list[dict[str, Any]] = []
        cursor = goal
        while (step := previous[cursor]) is not None:
            before, kind, direction = step
            hops_out.append({"from": before, "edge": kind, "dir": direction, "to": cursor})
            cursor = before
        hops_out.reverse()
        return {"found": True, "hops": hops_out, "length": len(hops_out)}

    def find(self, name: str, limit: int = 20) -> dict[str, Any]:
        needle = (name or "").strip().lower()
        if not needle:
            raise ToolFailure("invalid", "name is required")
        ranked: Counter[str] = Counter()
        for n in self.graph["nodes"]:
            label = n["label"].lower()
            path = (n.get("path") or "").lower()
            if needle in (label, label.rsplit(".", 1)[-1]):
                ranked[n["id"]] = 3
            elif needle in label or (n["kind"] == "file" and needle in path):
                ranked[n["id"]] = 1
        best = sorted(ranked, key=lambda i: (-ranked[i], len(i), i))[:limit]
        return {"matches": [brief(self.nodes[i]) for i in best], "total": len(ranked)}
