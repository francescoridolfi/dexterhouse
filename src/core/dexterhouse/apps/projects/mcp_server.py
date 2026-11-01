# SPDX-License-Identifier: AGPL-3.0-or-later
"""`dexterhouse-project`: the built-in MCP server behind `project.*` and `skills.read`.

Started by the agents runtime over stdio, one process per turn, with the project and the
turn in `DH_PROJECT_ID` / `DH_TURN_ID` (interpolations of `src/builtin/tools/project` and
`src/builtin/tools/skills`). The argument `project` or `skills` selects the tools to expose,
since each tool package owns one permission prefix. Services: `projects.services.tools`.
"""

import os
import sys
import uuid
from typing import Any

from asgiref.sync import sync_to_async
from mcp.server.mcpserver import MCPServer

GROUPS = ("project", "skills")


def build_server(project_id: uuid.UUID, turn_id: uuid.UUID, group: str = "project") -> MCPServer:
    from dexterhouse.apps.projects.services import tools

    ctx = tools.ToolContext(project_id=project_id, turn_id=turn_id)
    server: MCPServer = MCPServer(f"dexterhouse-{group}", version="0.1.0")

    def call(function: Any, *args: Any, **kwargs: Any) -> Any:
        return sync_to_async(function)(ctx, *args, **kwargs)

    if group == "skills":

        @server.tool(name="skills_read", description="Read a skill or one of its files.")
        async def skills_read(name: str, path: str = "SKILL.md") -> dict[str, Any]:
            return await call(tools.read_skill, name, path)

        return server

    @server.tool(name="project_artifact", description="Read one artifact of the project.")
    async def project_artifact(
        kind: str, name: str | None = None, version: str = "latest", section: str | None = None
    ) -> dict[str, Any]:
        return await call(tools.artifact, kind, name, version, section)

    @server.tool(name="project_artifacts", description="List the project's artifacts.")
    async def project_artifacts(kind: str | None = None) -> dict[str, Any]:
        return await call(tools.artifacts, kind)

    @server.tool(name="project_tasks", description="The task board with states and iterations.")
    async def project_tasks(status: str | None = None) -> dict[str, Any]:
        return await call(tools.tasks, status)

    @server.tool(name="project_notes", description="The user's notes for this phase.")
    async def project_notes(unconsumed_only: bool = True) -> dict[str, Any]:
        return await call(tools.notes, unconsumed_only)

    @server.tool(name="project_ask", description="Ask the human structured questions.")
    async def project_ask(questions: list[dict[str, Any]]) -> dict[str, Any]:
        return await call(tools.ask, questions)

    return server


def main(argv: list[str] | None = None) -> int:
    import django

    args = sys.argv[1:] if argv is None else argv
    group = args[0] if args else "project"
    if group not in GROUPS:
        sys.stderr.write(f"dexterhouse-project: unknown group {group!r}\n")
        return 1
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dexterhouse.settings.prod")
    django.setup()
    try:
        project_id = uuid.UUID(os.environ["DH_PROJECT_ID"])
        turn_id = uuid.UUID(os.environ["DH_TURN_ID"])
    except (KeyError, ValueError) as exc:
        sys.stderr.write(f"dexterhouse-project: DH_PROJECT_ID/DH_TURN_ID required: {exc}\n")
        return 1
    build_server(project_id, turn_id, group).run("stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
