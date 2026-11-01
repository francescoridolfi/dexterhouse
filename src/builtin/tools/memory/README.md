# memory

Built-in MCP server (`runs_in: worker`) giving agents relevance search over their project:
artifacts chunked by heading or item, gate comments and retrospective lessons (weight 1.5).

| Permission | Arguments | Returns |
|---|---|---|
| `memory.search` | `query`, `k=8`, `kinds?[]`, `min_score=0.3` | `hits[]` with `artifact{id, kind, name, version}`, `score`, `weight`, `content`; `warnings[]` |
| `memory.recent` | `kinds?[]`, `limit=10` | latest indexed sources with an excerpt |

Search is scoped to the turn's project and only compares chunks made by the current
embedder; after an embedder change it returns `reindex_required` until the project is
re-indexed. Server code: `dexterhouse.apps.memory.mcp_server`.
