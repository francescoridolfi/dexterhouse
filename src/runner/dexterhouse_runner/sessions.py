# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP sessions with the servers inside the workspaces (infra/runner_protocol.md).

One stdio session per (workspace, server): `docker exec -i <container> <command>`, opened on
first use and kept open; the built-in server is `dexterhouse-workspace-mcp`. A session that
dies is restarted on the next call (that call returns `internal`); a fourth death within
five minutes marks the workspace broken. Third-party servers close after 10 minutes idle.
The SDK is asyncio-based: the pool owns an event loop in a thread and every session is owned
by a single task (anyio cancel scopes must exit where they entered).
"""

import asyncio
import json
import threading
import time
from collections import deque
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Any

import structlog
from mcp import Client, StdioServerParameters

logger = structlog.get_logger(__name__)

CONNECT_TIMEOUT_S = 60.0
MAX_RESTARTS = 3
RESTART_WINDOW_S = 300.0
THIRD_PARTY_IDLE_S = 600.0
BUILTIN = "workspace"


class SessionError(RuntimeError):
    """The server could not start or stopped; `broken` after too many restarts."""

    def __init__(self, detail: str, *, broken: bool = False) -> None:
        super().__init__(detail)
        self.broken = broken


@dataclass(frozen=True)
class Listed:
    name: str
    description: str
    input_schema: dict[str, Any]


class _Session:
    def __init__(self, spec: StdioServerParameters) -> None:
        self.spec = spec
        self.used_at = time.monotonic()
        self.requests: asyncio.Queue[tuple[str, dict[str, Any], asyncio.Future[Any]] | None] = (
            asyncio.Queue()
        )
        self.ready: asyncio.Future[list[Listed]] = asyncio.get_running_loop().create_future()
        self.task = asyncio.create_task(self._serve())

    async def _serve(self) -> None:
        try:
            async with Client(self.spec, read_timeout_seconds=1000) as client:
                listed = await client.list_tools()
                self.ready.set_result(
                    [Listed(t.name, t.description or "", t.input_schema) for t in listed.tools]
                )
                while (item := await self.requests.get()) is not None:
                    name, args, future = item
                    try:
                        future.set_result(await client.call_tool(name, args))
                    except Exception as exc:
                        # Tool failures come back as results: an exception is the session's
                        # own (connection closed, protocol error), so it ends here.
                        future.set_exception(exc)
                        raise
        except Exception as exc:
            if not self.ready.done():
                self.ready.set_exception(exc)
            while not self.requests.empty():
                pending = self.requests.get_nowait()
                if pending is not None and not pending[2].done():
                    pending[2].set_exception(SessionError(f"MCP server stopped: {exc}"))
            logger.warning("runner.mcp_session_closed", error=str(exc))

    async def call(self, name: str, args: dict[str, Any]) -> Any:
        if self.task.done():
            raise SessionError("MCP server is not running")
        self.used_at = time.monotonic()
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        await self.requests.put((name, args, future))
        return await future

    async def close(self) -> None:
        await self.requests.put(None)
        try:
            await asyncio.wait_for(self.task, timeout=10)
        except (TimeoutError, asyncio.CancelledError):
            self.task.cancel()


class SessionPool:
    def __init__(self, docker_cli: str = "docker") -> None:
        self.docker_cli = docker_cli
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="mcp-pool", daemon=True)
        self._thread.start()
        self._sessions: dict[tuple[str, str], _Session] = {}
        self._deaths: dict[str, deque[float]] = {}

    def spec(
        self, container: str, command: list[str], env: dict[str, str] | None = None
    ) -> StdioServerParameters:
        args = ["exec", "-i", "-u", "1000:1000", "-w", "/workspace"]
        for key, value in (env or {}).items():
            args += ["-e", f"{key}={value}"]
        return StdioServerParameters(command=self.docker_cli, args=[*args, container, *command])

    def _run(self, coro: Any, timeout: float) -> Any:
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout)
        except FutureTimeout as exc:
            future.cancel()
            raise TimeoutError(f"MCP call timed out after {timeout:.0f}s") from exc

    def _died(self, workspace_id: str) -> bool:
        """Record a dead session; True when the workspace exceeded its restarts."""
        now = time.monotonic()
        deaths = self._deaths.setdefault(workspace_id, deque())
        deaths.append(now)
        while deaths and now - deaths[0] > RESTART_WINDOW_S:
            deaths.popleft()
        return len(deaths) > MAX_RESTARTS

    async def _session(self, key: tuple[str, str], spec: StdioServerParameters) -> _Session:
        session = self._sessions.get(key)
        if session is not None and session.task.done():
            del self._sessions[key]
            if self._died(key[0]):
                raise SessionError("the workspace MCP server keeps crashing", broken=True)
            raise SessionError("the workspace MCP server stopped; it restarts on the next call")
        if session is None:
            session = _Session(spec)
            self._sessions[key] = session
            logger.info("runner.mcp_session_started", workspace_id=key[0], server=key[1])
        return session

    def list_tools(
        self, workspace_id: str, server: str, spec: StdioServerParameters
    ) -> list[Listed]:
        async def run() -> list[Listed]:
            session = await self._session((workspace_id, server), spec)
            return await session.ready

        try:
            return self._run(run(), CONNECT_TIMEOUT_S)
        except SessionError:
            raise
        except Exception as exc:
            raise SessionError(f"cannot start the MCP server {server}: {exc}") from exc

    def call(
        self,
        workspace_id: str,
        server: str,
        spec: StdioServerParameters,
        tool: str,
        args: dict[str, Any],
        timeout_s: float,
    ) -> dict[str, Any]:
        """Call `tool`; returns the JSON object it answered (`{"error": …}` on failure)."""

        async def run() -> Any:
            session = await self._session((workspace_id, server), spec)
            await session.ready
            return await session.call(tool, args)

        try:
            result = self._run(run(), timeout_s)
        except (SessionError, TimeoutError):
            raise
        except Exception as exc:
            raise SessionError(f"MCP call failed: {exc}") from exc
        return decode(result)

    def close_workspace(self, workspace_id: str) -> None:
        keys = [k for k in self._sessions if k[0] == workspace_id]
        for key in keys:
            session = self._sessions.pop(key)
            try:
                self._run(session.close(), 15)
            except TimeoutError:
                logger.warning("runner.mcp_session_close_timeout", workspace_id=workspace_id)
        self._deaths.pop(workspace_id, None)

    def close_idle(self, idle_s: float = THIRD_PARTY_IDLE_S) -> int:
        now = time.monotonic()
        idle = [
            k for k, s in self._sessions.items() if k[1] != BUILTIN and now - s.used_at > idle_s
        ]
        for key in idle:
            session = self._sessions.pop(key)
            try:
                self._run(session.close(), 15)
            except TimeoutError:
                pass
        return len(idle)

    def third_party_count(self, workspace_id: str) -> int:
        return sum(1 for k in self._sessions if k[0] == workspace_id and k[1] != BUILTIN)

    def has(self, workspace_id: str, server: str) -> bool:
        return (workspace_id, server) in self._sessions


def decode(result: Any) -> dict[str, Any]:
    """The JSON object of a `CallToolResult` (text block or structured content)."""
    structured = getattr(result, "structured_content", None)
    texts = [b.text for b in getattr(result, "content", []) if getattr(b, "text", None) is not None]
    if isinstance(structured, dict) and "result" not in structured:
        data: Any = structured
    else:
        try:
            data = json.loads("\n".join(texts)) if texts else structured
        except json.JSONDecodeError:
            data = {"text": "\n".join(texts)}
    if getattr(result, "is_error", False) and not (isinstance(data, dict) and "error" in data):
        return {"error": {"code": "internal", "detail": "\n".join(texts)[:2000]}}
    return data if isinstance(data, dict) else {"result": data}
