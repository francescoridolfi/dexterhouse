# SPDX-License-Identifier: AGPL-3.0-or-later
"""`dexterhouse-builtin`: the built-in MCP tools of a turn in a single process.

The three built-in tool packages (`memory`, `project`, `skills`) declare the same command,
so the agents runtime starts one stdio server per turn instead of one per package: the
Django bootstrap of a server process costs more than a second, and a turn used to pay it
up to three times. Each permission still maps to its own MCP tool name; the catalog of the
tool packages decides what an agent may call.

Environment (from the `${project.*}` interpolations of the tool packages):
`DH_PROJECT_ID`, `DH_ORGANIZATION_ID`, `DH_TURN_ID`, `DH_DATA_RESIDENCY` (default `any`).
"""

import os
import sys
import uuid

from mcp.server.mcpserver import MCPServer


def build_server(
    project_id: uuid.UUID,
    organization_id: uuid.UUID,
    turn_id: uuid.UUID,
    data_residency: str = "any",
) -> MCPServer:
    from dexterhouse.apps.memory.mcp_server import register_memory_tools
    from dexterhouse.apps.projects.mcp_server import register_project_tools

    server: MCPServer = MCPServer("dexterhouse-builtin", version="0.1.0")
    register_memory_tools(server, project_id, organization_id, data_residency)
    register_project_tools(server, project_id, turn_id, "project")
    register_project_tools(server, project_id, turn_id, "skills")
    return server


def main() -> int:
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dexterhouse.settings.prod")
    django.setup()
    try:
        project_id = uuid.UUID(os.environ["DH_PROJECT_ID"])
        organization_id = uuid.UUID(os.environ["DH_ORGANIZATION_ID"])
        turn_id = uuid.UUID(os.environ["DH_TURN_ID"])
    except (KeyError, ValueError) as exc:
        sys.stderr.write(
            "dexterhouse-builtin: DH_PROJECT_ID, DH_ORGANIZATION_ID and DH_TURN_ID "
            f"required: {exc}\n"
        )
        return 1
    build_server(
        project_id, organization_id, turn_id, os.environ.get("DH_DATA_RESIDENCY", "any")
    ).run("stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
