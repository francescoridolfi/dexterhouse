# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP tools of the groups `marketplace` (search, details) and `packages` (installed,
propose, install), served by the combined per-turn process
(`dexterhouse.apps.agents.builtin_mcp`). Services: `packages.services.marketplace` and
`packages.services.recruiting`; a refused call raises and reaches the agent as an error.
"""

import uuid
from typing import Any

from asgiref.sync import sync_to_async
from mcp.server.mcpserver import MCPServer

GROUPS = ("marketplace", "packages")


def register_package_tools(
    server: MCPServer, project_id: uuid.UUID, organization_id: uuid.UUID, group: str
) -> None:
    from dexterhouse.apps.packages.services import marketplace, recruiting
    from dexterhouse.apps.projects.services.tools import ToolError

    ctx = recruiting.RecruitingContext(project_id=project_id, organization_id=organization_id)

    if group == "marketplace":

        @server.tool(name="marketplace_search", description="Search the package marketplace.")
        async def marketplace_search(
            query: str = "",
            kind: str | None = None,
            tags: list[str] | None = None,
            verified_only: bool = False,
            min_rating: float | None = None,
            limit: int = 10,
        ) -> dict[str, Any]:
            return await sync_to_async(marketplace.search)(
                query, kind, tags, verified_only, min_rating, limit
            )

        @server.tool(name="marketplace_details", description="Details of a marketplace package.")
        async def marketplace_details(name: str) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                try:
                    return marketplace.details(name, organization_id)
                except (
                    marketplace.MarketplaceUnavailableError,
                    marketplace.PackageNotFoundError,
                ) as exc:
                    raise ToolError(str(exc)) from exc

            return await sync_to_async(run)()

        return

    @server.tool(name="packages_installed", description="Packages installed in the organization.")
    async def packages_installed(kind: str | None = None) -> dict[str, Any]:
        return await sync_to_async(recruiting.installed)(ctx, kind)

    @server.tool(name="packages_propose", description="Record the packages you propose.")
    async def packages_propose(proposals: list[dict[str, Any]]) -> dict[str, Any]:
        return await sync_to_async(recruiting.propose)(ctx, proposals)

    @server.tool(name="packages_install", description="Install a verified low-risk package.")
    async def packages_install(name: str, version: str = "") -> dict[str, Any]:
        return await sync_to_async(recruiting.install)(ctx, name, version)
