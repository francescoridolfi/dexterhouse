# SPDX-License-Identifier: AGPL-3.0-or-later
"""`code_graph`: the dependency graph of the workspace (`code_graph.json`, system-produced).

Built deterministically by the runner's `workspace.graph` extractor after each agent
commit (no LLM). Contract shared with the frontend viewer: node ids are unique, every
edge and `parent` points to an existing node, `stats` counts files, symbols and edges.
Example: `tests/fixtures/artifacts/code_graph.json`.
"""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from dexterhouse_schema.common import NonEmptyStr, StrictModel

NodeKind = Literal["file", "module", "symbol", "external"]
EdgeKind = Literal["imports", "defines", "calls", "inherits", "tests"]
Count = Annotated[int, Field(ge=0)]


class GraphNode(StrictModel):
    id: NonEmptyStr
    kind: NodeKind
    label: str
    path: str | None = None
    lang: str | None = None
    line: Annotated[int, Field(ge=1)] | None = None
    symbol_kind: str | None = None
    parent: str | None = None
    community: Count | None = None


class GraphEdge(StrictModel):
    source: NonEmptyStr
    target: NonEmptyStr
    kind: EdgeKind


class GraphStats(StrictModel):
    files: Count
    symbols: Count
    edges: Count


class CodeGraph(StrictModel):
    schema_version: Literal[1] = Field(alias="schema")
    commit: Annotated[str, Field(pattern=r"^([0-9a-f]{40}|[0-9a-f]{64})?$")]
    generated_at: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")]
    stats: GraphStats
    nodes: list[GraphNode]
    edges: list[GraphEdge]

    @model_validator(mode="after")
    def _consistent(self) -> "CodeGraph":
        ids = {n.id for n in self.nodes}
        if len(ids) != len(self.nodes):
            raise ValueError("node ids must be unique")
        dangling = sorted(
            {e.source for e in self.edges} - ids
            | {e.target for e in self.edges} - ids
            | {n.parent for n in self.nodes if n.parent is not None} - ids
        )
        if dangling:
            raise ValueError(f"edges or parents point to unknown nodes: {dangling[:5]}")
        counted = (
            sum(n.kind == "file" for n in self.nodes),
            sum(n.kind == "symbol" for n in self.nodes),
            len(self.edges),
        )
        if counted != (self.stats.files, self.stats.symbols, self.stats.edges):
            raise ValueError(f"stats do not match the graph: {counted}")
        return self
