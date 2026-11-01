# SPDX-License-Identifier: AGPL-3.0-or-later
"""`dexterhouse-memory`: the built-in MCP server behind `memory.*` (contracts/tools/memory.md).

Started by the agents runtime over stdio, one process per turn, with the project in
`DH_PROJECT_ID` / `DH_ORGANIZATION_ID` (from the `${project.*}` interpolations of
`src/builtin/tools/memory/tool.yaml`). It never sees other projects.
"""

import os
import sys
import uuid
from typing import Any

from asgiref.sync import sync_to_async
from mcp.server.mcpserver import MCPServer

UNTRUSTED_OPEN = "<<untrusted source={source}>>"
UNTRUSTED_CLOSE = "<</untrusted>>"


def wrap_untrusted(text: str, source: str) -> str:
    """Content from outside the project stays data, never instructions (threat model)."""
    return f"{UNTRUSTED_OPEN.format(source=source)}\n{text}\n{UNTRUSTED_CLOSE}"


def build_server(
    project_id: uuid.UUID,
    organization_id: uuid.UUID,
    data_residency: str = "any",
    embedder: Any = None,
) -> MCPServer:
    from dexterhouse.apps.gateway.embeddings import resolve_embedder
    from dexterhouse.apps.memory.services.search import recent, search

    server: MCPServer = MCPServer("dexterhouse-memory", version="0.1.0")
    state: dict[str, Any] = {"embedder": embedder}

    def _search(query: str, k: int, kinds: list[str] | None, min_score: float) -> dict[str, Any]:
        if state["embedder"] is None:
            state["embedder"] = resolve_embedder(
                organization_id,
                project_id,
                data_residency="local" if data_residency == "local" else "any",
            )
        result = search(
            project_id=project_id,
            query=query,
            embedder=state["embedder"],
            k=k,
            kinds=kinds,
            min_score=min_score,
        )
        hits = []
        for hit in result.hits:
            item = hit.as_dict()
            if hit.untrusted:
                item["content"] = wrap_untrusted(hit.content, hit.name or hit.kind)
            hits.append(item)
        return {"hits": hits, "warnings": result.warnings}

    @server.tool(name="memory_search", description="Search the project memory by relevance.")
    async def memory_search(
        query: str, k: int = 8, kinds: list[str] | None = None, min_score: float = 0.3
    ) -> dict[str, Any]:
        return await sync_to_async(_search)(query, k, kinds, min_score)

    @server.tool(name="memory_recent", description="Latest indexed sources of the project.")
    async def memory_recent(kinds: list[str] | None = None, limit: int = 10) -> dict[str, Any]:
        items = await sync_to_async(recent)(project_id=project_id, kinds=kinds, limit=limit)
        return {"items": items}

    return server


def main() -> int:
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dexterhouse.settings.prod")
    django.setup()
    try:
        project_id = uuid.UUID(os.environ["DH_PROJECT_ID"])
        organization_id = uuid.UUID(os.environ["DH_ORGANIZATION_ID"])
    except (KeyError, ValueError) as exc:
        sys.stderr.write(f"dexterhouse-memory: DH_PROJECT_ID/DH_ORGANIZATION_ID required: {exc}\n")
        return 1
    server = build_server(project_id, organization_id, os.environ.get("DH_DATA_RESIDENCY", "any"))
    server.run("stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
