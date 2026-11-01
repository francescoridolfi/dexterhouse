# SPDX-License-Identifier: AGPL-3.0-or-later
"""Echo MCP server for tests: logs every call next to itself, so tests can count them."""

import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer

LOG = Path(__file__).with_name("calls.log")
server = MCPServer("echo")


def _log(name: str) -> None:
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"{name} {os.environ.get('ECHO_PROJECT', '')}\n")


@server.tool()
def say(text: str) -> str:
    _log("say")
    return f"echo: {text}"


@server.tool()
def write(path: str, content: str) -> str:
    _log("write")
    return f"wrote {len(content)} chars to {path}"


@server.tool()
def fail() -> str:
    _log("fail")
    raise ValueError("boom")


if __name__ == "__main__":
    server.run("stdio")
