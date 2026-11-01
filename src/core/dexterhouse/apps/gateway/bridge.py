# SPDX-License-Identifier: AGPL-3.0-or-later
"""`dexterhouse-mcp-bridge`: the stdio MCP server the Claude Code CLI sees (provider_cli.md).

It exposes exactly the tools the turn may use (`DH_BRIDGE_TOOLS`, a JSON list of `ToolSpec`
signed by `DH_TURN_TOKEN`) and intercepts every call: nothing is executed here. The CLI runs
with `--max-turns 1`, so the turn stops at the `tool_use`; the gateway hands the call to the
agents runtime, which applies permissions, idempotency and events, and sends the result in
the next CLI invocation.
"""

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import anyio
import jwt
import mcp_types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from dexterhouse.apps.gateway.tokens import verify_turn_token

DEFERRED = (
    "Deferred: DexterHouse executes this tool call and returns its result in the next "
    "message. Stop here."
)


def load_specs(environ: dict[str, str]) -> list[dict[str, Any]]:
    """Verify the token against the tool list and return the specs.

    Raises:
        jwt.InvalidTokenError: missing, expired or forged token.
    """
    raw = Path(environ["DH_BRIDGE_TOOLS"]).read_bytes()
    verify_turn_token(
        environ.get("DH_TURN_TOKEN", ""),
        key=environ.get("DH_BRIDGE_KEY", ""),
        tools_sha256=hashlib.sha256(raw).hexdigest(),
    )
    return json.loads(raw)


def build_server(specs: list[dict[str, Any]]) -> Server[Any]:
    tools = [
        types.Tool(
            name=s["name"], description=s.get("description", ""), input_schema=s["input_schema"]
        )
        for s in specs
    ]
    names = {t.name for t in tools}

    async def list_tools(ctx: Any, params: Any) -> types.ListToolsResult:
        return types.ListToolsResult(tools=tools)

    async def call_tool(ctx: Any, params: Any) -> types.CallToolResult:
        if params.name not in names:
            return types.CallToolResult(
                content=[types.TextContent(text=f"tool {params.name} is not allowed")],
                is_error=True,
            )
        return types.CallToolResult(content=[types.TextContent(text=DEFERRED)])

    return Server("dexterhouse", on_list_tools=list_tools, on_call_tool=call_tool)


async def _serve(server: Server[Any]) -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> int:
    try:
        specs = load_specs(dict(os.environ))
    except (KeyError, OSError, jwt.InvalidTokenError) as exc:
        sys.stderr.write(f"dexterhouse-mcp-bridge: refusing to start: {exc}\n")
        return 1
    anyio.run(_serve, build_server(specs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
