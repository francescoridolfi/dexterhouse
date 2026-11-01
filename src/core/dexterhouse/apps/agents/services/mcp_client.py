# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP client for the tools of a turn (ADR-0003): stdio and Streamable HTTP servers.

A `McpPool` lives for one turn: each distinct server (command, arguments, environment and
working directory) gets one connection, opened on first use and kept until the turn ends, so a
stdio server process starts once per turn, not per call, and tool packages that declare the
same server (the built-in `memory`, `project` and `skills`) share one process.
The SDK is asyncio-based; the pool runs its own event loop in a thread and every
connection is owned by a single task (anyio cancel scopes must exit where they entered).
"""

import asyncio
import json
import os
import re
import sys
import threading
from collections.abc import Mapping
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Any

import structlog
from mcp import Client, StdioServerParameters

from dexterhouse.apps.agents.services.packages import ToolBinding

logger = structlog.get_logger(__name__)

DEFAULT_TIMEOUT_S = 120.0
CONNECT_TIMEOUT_S = 60.0
#: Core settings a built-in worker server needs to reach the database and the embedder.
CORE_ENV = (
    "DJANGO_SETTINGS_MODULE",
    "DATABASE_URL",
    "DATABASE_PASSWORD_FILE",
    "SECRET_KEY",
    "SECRET_KEY_FILE",
    "REDIS_URL",
    "OLLAMA_BASE_URL",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_COMPATIBLE_BASE_URL",
    "OPENAI_COMPATIBLE_API_KEY",
    "PRICES_FILE",
    "FX_EUR_PER_USD",
    "BUILTIN_DIR",
    # registry and package store (marketplace.*, packages.*)
    "PACKAGES_DIR",
    "REGISTRY_INDEX_URL",
    "PACKAGES_ALLOW_LOCAL",
    "PACKAGES_GIT_MIRRORS",
    "MARKETPLACE_URL",
    "MARKETPLACE_RAW_URL",
    # the same, for the processes started by end-to-end tests (settings/test.py)
    "DH_TEST_PACKAGES_DIR",
    "DH_TEST_REGISTRY_INDEX_URL",
    "DH_TEST_PACKAGES_GIT_MIRRORS",
    "DH_TEST_MARKETPLACE_RAW_URL",
)
_INTERPOLATION = re.compile(r"\$\{([a-z_.]+)\}")


class McpError(RuntimeError):
    """The server could not be reached or crashed: the turn retries (transient)."""


@dataclass(frozen=True)
class ToolOutcome:
    content: str
    is_error: bool = False
    structured: Any = None


@dataclass(frozen=True)
class RemoteTool:
    name: str
    description: str
    input_schema: dict[str, Any]


def interpolate(value: str, variables: Mapping[str, str]) -> str:
    """`${project.id}`-style values; unknown names become empty strings."""
    return _INTERPOLATION.sub(lambda m: variables.get(m[1], ""), value)


def server_spec(binding: ToolBinding, variables: Mapping[str, str]) -> StdioServerParameters | str:
    """How to start or reach the package's server."""
    tool = binding.tool
    if tool.transport == "http":
        return interpolate(str(tool.url), variables)
    command = list(tool.command or [])
    if command[0] == "python":
        command[0] = sys.executable  # the worker's interpreter, with the core installed
    elif "/" in command[0]:
        command[0] = str(binding.root / command[0])
    env = {name: interpolate(value, variables) for name, value in tool.env.items()}
    if binding.builtin:
        env |= {name: os.environ[name] for name in CORE_ENV if name in os.environ}
        cwd = None  # an installed module of the worker: no package directory needed
    else:
        cwd = binding.root
    return StdioServerParameters(command=command[0], args=command[1:], env=env, cwd=cwd)


def spec_key(spec: StdioServerParameters | str) -> str:
    """Identity of a server: two bindings with the same key share one connection."""
    if isinstance(spec, str):
        return spec
    return json.dumps(
        {"command": spec.command, "args": spec.args, "env": spec.env, "cwd": str(spec.cwd or "")},
        sort_keys=True,
    )


class _Connection:
    """One task owning one `Client`; requests arrive through a queue."""

    def __init__(self, spec: StdioServerParameters | str, timeout_s: float) -> None:
        self.spec = spec
        self.timeout_s = timeout_s
        self.requests: asyncio.Queue[tuple[str, dict[str, Any], asyncio.Future[Any]] | None] = (
            asyncio.Queue()
        )
        self.ready: asyncio.Future[list[RemoteTool]] = asyncio.get_running_loop().create_future()
        self.task = asyncio.create_task(self._serve())

    async def _serve(self) -> None:
        try:
            async with Client(self.spec, read_timeout_seconds=self.timeout_s) as client:
                listed = await client.list_tools()
                self.ready.set_result(
                    [RemoteTool(t.name, t.description or "", t.input_schema) for t in listed.tools]
                )
                while (item := await self.requests.get()) is not None:
                    name, args, future = item
                    try:
                        future.set_result(await client.call_tool(name, args))
                    except Exception as exc:  # delivered to the caller, which decides
                        future.set_exception(exc)
        except Exception as exc:
            if not self.ready.done():
                self.ready.set_exception(exc)
            while not self.requests.empty():
                pending = self.requests.get_nowait()
                if pending is not None and not pending[2].done():
                    pending[2].set_exception(McpError(f"MCP server stopped: {exc}"))
            logger.warning("agents.mcp_connection_closed", error=str(exc))

    async def call(self, name: str, args: dict[str, Any]) -> Any:
        if self.task.done():
            raise McpError("MCP server is not running")
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        await self.requests.put((name, args, future))
        return await future

    async def close(self) -> None:
        await self.requests.put(None)
        try:
            await asyncio.wait_for(self.task, timeout=10)
        except (TimeoutError, asyncio.CancelledError):
            self.task.cancel()


class McpPool:
    """Connections to the tool servers of one turn; use as a context manager."""

    def __init__(self, variables: Mapping[str, str], timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        self.variables = dict(variables)
        self.timeout_s = timeout_s
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="mcp-pool", daemon=True)
        self._thread.start()
        self._connections: dict[str, _Connection] = {}

    def __enter__(self) -> "McpPool":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _run(self, coro: Any, timeout: float) -> Any:
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout)
        except FutureTimeout as exc:
            future.cancel()
            raise TimeoutError(f"MCP call timed out after {timeout}s") from exc

    async def _connection(self, binding: ToolBinding) -> _Connection:
        spec = server_spec(binding, self.variables)
        key = spec_key(spec)
        connection = self._connections.get(key)
        if connection is None or connection.task.done():
            connection = _Connection(spec, self.timeout_s)
            self._connections[key] = connection
            logger.info(
                "agents.mcp_server_started",
                server=spec if isinstance(spec, str) else [spec.command, *spec.args],
                tool=binding.tool.name,
            )
        return connection

    def list_tools(self, binding: ToolBinding) -> list[RemoteTool]:
        """Tools exposed by the package's server (connects if needed)."""

        async def run() -> list[RemoteTool]:
            connection = await self._connection(binding)
            return await connection.ready

        try:
            return self._run(run(), CONNECT_TIMEOUT_S)
        except (OSError, TimeoutError, McpError) as exc:
            raise McpError(f"cannot start {binding.tool.name}: {exc}") from exc
        except Exception as exc:
            raise McpError(f"cannot start {binding.tool.name}: {exc}") from exc

    def call(
        self, binding: ToolBinding, args: dict[str, Any], timeout_s: float | None = None
    ) -> ToolOutcome:
        """Invoke the permission's MCP tool; tool-level errors come back as `is_error`."""
        timeout = timeout_s or self.timeout_s

        async def run() -> Any:
            connection = await self._connection(binding)
            await connection.ready
            return await connection.call(binding.permission.mcp_tool, args)

        result = self._run(run(), timeout + 5)
        return to_outcome(result)

    def close(self) -> None:
        if self._loop.is_closed():
            return

        async def shutdown() -> None:
            await asyncio.gather(
                *(c.close() for c in self._connections.values()), return_exceptions=True
            )

        try:
            self._run(shutdown(), 15)
        except TimeoutError:
            logger.warning("agents.mcp_pool_close_timeout")
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(5)
        self._loop.close()


def to_outcome(result: Any) -> ToolOutcome:
    """Flatten a `CallToolResult`: its text blocks, else the structured content as JSON."""
    structured = getattr(result, "structured_content", None)
    texts = [b.text for b in getattr(result, "content", []) if getattr(b, "text", None) is not None]
    if texts:
        content = "\n".join(texts)
    elif structured is not None:
        content = json.dumps(structured, ensure_ascii=False, default=str)
    else:
        content = ""
    is_error = bool(getattr(result, "is_error", False))
    return ToolOutcome(content=content, is_error=is_error, structured=structured)
