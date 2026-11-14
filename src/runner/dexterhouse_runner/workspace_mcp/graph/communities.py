# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deterministic communities: label propagation over the file graph.

Files start labelled by directory; each round (sorted order, at most 20) a file takes the
label most frequent among its neighbours (ties: the smaller label). Symbol edges count for
their files. Communities are numbered from 0 by size, then by first path; symbols take
their file's community, modules the most common one of their files; externals none.
"""

from collections import Counter, defaultdict
from typing import Any

MAX_ROUNDS = 20


def _file_of(nid: str, nodes: dict[str, dict[str, Any]]) -> str | None:
    if nid.startswith("file:"):
        return nid
    if nid.startswith("sym:"):
        return "file:" + str(nodes[nid]["path"])
    return None


def communities(nodes: dict[str, dict[str, Any]], edges: set[tuple[str, str, str]]) -> dict:
    files = sorted(n for n in nodes if n.startswith("file:"))
    by_module: dict[str, list[str]] = defaultdict(list)
    for fid in files:
        by_module[str(nodes[fid]["parent"])].append(fid)
    adjacency: dict[str, Counter[str]] = {f: Counter() for f in files}
    for source, target, kind in edges:
        if kind == "defines":
            continue
        a = _file_of(source, nodes)
        targets = by_module.get(target, []) if target.startswith("module:") else [target]
        for b in (_file_of(t, nodes) for t in targets):
            if a and b and a != b:
                adjacency[a][b] += 1
                adjacency[b][a] += 1
    start = {module: index for index, module in enumerate(sorted(by_module))}
    label = {f: start[str(nodes[f]["parent"])] for f in files}
    for _ in range(MAX_ROUNDS):
        changed = False
        for fid in files:
            votes: Counter[int] = Counter()
            for other, weight in adjacency[fid].items():
                votes[label[other]] += weight
            if not votes:
                continue
            best = min(votes, key=lambda lab: (-votes[lab], lab))
            if votes[best] > votes.get(label[fid], 0) and best != label[fid]:
                label[fid] = best
                changed = True
        if not changed:
            break
    groups: dict[int, list[str]] = defaultdict(list)
    for fid in files:
        groups[label[fid]].append(fid)
    order = sorted(groups.values(), key=lambda g: (-len(g), g[0]))
    out: dict[str, int] = {fid: index for index, group in enumerate(order) for fid in group}
    for nid, data in nodes.items():
        if nid.startswith("sym:"):
            out[nid] = out["file:" + str(data["path"])]
    for module, members in by_module.items():
        if module in nodes and members:
            out[module] = Counter(out[m] for m in members).most_common(1)[0][0]
    return out
