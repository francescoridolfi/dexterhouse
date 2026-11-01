# SPDX-License-Identifier: AGPL-3.0-or-later
"""`anthropic-cli`: Claude Code CLI as an LLM provider in the worker (CD-012, CD-025).

One `claude -p --max-turns 1` process per gateway call. The CLI's native tools are disabled;
our tools reach the model through `dexterhouse-mcp-bridge`, which intercepts every call, so
the tool-use loop stays in the agents runtime. The conversation so far is sent as a single
stream-json user message (a transcript): the CLI cannot be given prior assistant turns.
Opt-in only: a profile must set `options.acknowledge_cli_terms: true` (provider_cli.md).
"""

import contextlib
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess  # nosec B404: the CLI is the provider; arguments are a fixed list
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import redis
import structlog
from django.conf import settings

from dexterhouse.apps.gateway.conf import get_gateway_env
from dexterhouse.apps.gateway.messages import (
    CompletionRequest,
    Stop,
    StopReason,
    StreamEvent,
    TextDelta,
    ToolCallDelta,
    ToolCallEnd,
    ToolCallPart,
    ToolCallStart,
    ToolResultPart,
    Usage,
)
from dexterhouse.apps.gateway.providers.base import (
    Capabilities,
    ProviderConfig,
    ProviderError,
    internal_tool_name,
    system_text,
    wire_tool_name,
)
from dexterhouse.apps.gateway.tokens import bridge_key, issue_turn_token

logger = structlog.get_logger(__name__)

CLI_MIN_VERSION = (2, 0, 0)
MCP_SERVER = "dexterhouse"
TOOL_PREFIX = f"mcp__{MCP_SERVER}__"
DISALLOWED_TOOLS = "Bash,Read,Write,Edit,MultiEdit,Glob,Grep,WebFetch,WebSearch,Task,NotebookEdit"
KILL_GRACE_S = 10
_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")
_AUTH_HINT = re.compile(
    r"/login|not (logged|authenticated)|invalid api key|authenticat|oauth", re.I
)
NOT_AUTHENTICATED = (
    "the Claude Code CLI is not authenticated on this worker: run `claude` once and log in "
    "(or `claude setup-token`), see docs/providers/anthropic-cli.md"
)


@dataclass(frozen=True)
class CliInfo:
    path: str
    version: tuple[int, int, int]


class AnthropicCliProvider:
    name = "anthropic-cli"

    def __init__(self, config: ProviderConfig | None = None) -> None:
        self.config = config or ProviderConfig()
        self.env = get_gateway_env()

    def capabilities(self) -> Capabilities:
        return Capabilities(tools=True, vision=False, max_context=200_000)

    def detect(self) -> CliInfo:
        """Locate the binary and check `claude --version` against `CLI_MIN_VERSION`.

        Raises:
            ProviderError: `configuration` when missing, unusable or too old.
        """
        path = shutil.which(self.config.options.get("cli_path") or self.env.CLAUDE_CLI_PATH)
        if path is None:
            raise ProviderError(
                "Claude Code CLI not found: install it on the worker or set CLAUDE_CLI_PATH",
                code="configuration",
            )
        try:
            out = subprocess.run(  # noqa: S603 # nosec B603: fixed argv (resolved binary), no shell
                [path, "--version"], capture_output=True, text=True, timeout=15, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ProviderError(
                f"cannot run {path} --version: {exc}", code="configuration"
            ) from exc
        match = _VERSION_RE.search(out.stdout or "")
        if match is None:
            raise ProviderError(
                f"unrecognised `claude --version`: {out.stdout!r}", code="configuration"
            )
        version = (int(match[1]), int(match[2]), int(match[3]))
        if version < CLI_MIN_VERSION:
            wanted = ".".join(map(str, CLI_MIN_VERSION))
            raise ProviderError(f"Claude Code CLI {match[0]} < {wanted}", code="configuration")
        return CliInfo(path=path, version=version)

    def stream(self, request: CompletionRequest) -> Iterator[StreamEvent]:
        info = self.detect()
        with tempfile.TemporaryDirectory(prefix="dh-turn-") as tmp:
            workdir = Path(tmp)
            argv = self.build_command(request, info.path, workdir)
            stdin = json.dumps(
                {"type": "user", "message": {"role": "user", "content": transcript(request)}}
            )
            with cli_slot(self.env.CLI_MAX_CONCURRENT):
                yield from self._run(argv, stdin, workdir)

    def build_command(self, request: CompletionRequest, path: str, workdir: Path) -> list[str]:
        """Write `system.md` (and `mcp.json` when the turn has tools) and return the argv."""
        system = workdir / "system.md"
        system.write_text(system_text(request), encoding="utf-8")
        (workdir / "cwd").mkdir()
        argv = [
            path,
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
            "--input-format",
            "stream-json",
            "--model",
            request.model,
            "--max-turns",
            "1",
            "--system-prompt-file",
            str(system),
            "--strict-mcp-config",
            "--tools",
            "",  # no built-in tool at all (the deny-list below alone leaves some enabled)
            "--disallowedTools",
            DISALLOWED_TOOLS,
            "--permission-mode",
            "dontAsk",
        ]
        if request.tools:
            argv += ["--mcp-config", str(self._write_mcp_config(request, workdir))]
            argv += ["--allowedTools", f"{TOOL_PREFIX}*"]
        return argv

    def _write_mcp_config(self, request: CompletionRequest, workdir: Path) -> Path:
        specs = [
            {
                "name": wire_tool_name(t.name),
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in request.tools
        ]
        tools = workdir / "tools.json"
        tools.write_text(json.dumps(specs), encoding="utf-8")
        key = bridge_key(settings.SECRET_KEY)
        token = issue_turn_token(
            key=key,
            turn_id=request.metadata.get("agent_turn_id"),
            tools_sha256=hashlib.sha256(tools.read_bytes()).hexdigest(),
        )
        config = {
            "mcpServers": {
                MCP_SERVER: {
                    "type": "stdio",
                    "command": sys.executable,
                    "args": ["-m", "dexterhouse.apps.gateway.bridge"],
                    "env": {
                        "DH_TURN_TOKEN": token,
                        "DH_BRIDGE_KEY": key,
                        "DH_BRIDGE_TOOLS": str(tools),
                    },
                }
            }
        }
        path = workdir / "mcp.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        path.chmod(0o600)
        return path

    def _process_env(self) -> dict[str, str]:
        env = {
            k: v for k, v in os.environ.items() if k not in {"ANTHROPIC_API_KEY", "DH_TURN_TOKEN"}
        }
        if self.env.CLAUDE_CLI_HOME:
            env["HOME"] = self.env.CLAUDE_CLI_HOME
        return env

    def _run(self, argv: list[str], stdin: str, workdir: Path) -> Iterator[StreamEvent]:
        timeout = int(self.config.options.get("timeout_s") or self.env.CLI_TIMEOUT_S)
        proc = subprocess.Popen(  # noqa: S603 # nosec B603: argv built by build_command, no shell
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=workdir / "cwd",
            env=self._process_env(),
            text=True,
        )
        expired = threading.Event()
        watchdog = threading.Timer(timeout, _terminate, args=(proc, expired))
        watchdog.start()
        try:
            if proc.stdin is None or proc.stdout is None:
                raise ProviderError("claude CLI pipes unavailable", retryable=True)
            proc.stdin.write(stdin + "\n")
            proc.stdin.close()
            yield from translate(proc.stdout)
        except ProviderError:
            raise
        except ValueError as exc:  # broken pipe after a kill
            raise ProviderError(f"claude CLI stream interrupted: {exc}", retryable=True) from exc
        finally:
            watchdog.cancel()
            if proc.poll() is None:
                _terminate(proc, None)
            stderr = proc.stderr.read() if proc.stderr else ""
            if stderr:
                logger.info("gateway.cli_stderr", stderr=stderr[-2000:])
            if expired.is_set():
                raise ProviderError(
                    f"claude CLI timed out after {timeout}s", status="timeout", retryable=True
                )


def _terminate(proc: subprocess.Popen[str], expired: threading.Event | None) -> None:
    if expired is not None:
        expired.set()
    proc.terminate()
    try:
        proc.wait(KILL_GRACE_S)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def transcript(request: CompletionRequest) -> str:
    """The non-system messages as one prompt; tool calls use the bridge's MCP names."""
    turns = [m for m in request.messages if m.role != "system"]
    if len(turns) == 1 and turns[0].role == "user":
        return turns[0].text()
    lines = ["<conversation>"]
    for message in turns:
        lines.append(f"[{message.role}]")
        for part in message.parts:
            if isinstance(part, ToolCallPart):
                name = TOOL_PREFIX + wire_tool_name(part.name)
                lines.append(f"[tool call {part.id}] {name} {json.dumps(part.args)}")
            elif isinstance(part, ToolResultPart):
                flag = " error" if part.is_error else ""
                lines.append(f"[tool result {part.call_id}{flag}]\n{part.content}")
            elif hasattr(part, "text"):
                lines.append(part.text)
    lines.append("</conversation>")
    lines.append(
        "Continue as the assistant: call a tool if needed, otherwise give the final answer."
    )
    return "\n".join(lines)


def translate(lines: Any) -> Iterator[StreamEvent]:
    """Map the CLI stream-json NDJSON to gateway events (provider_cli.md table)."""
    calls = 0
    result: dict[str, Any] | None = None
    for raw in lines:
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            logger.info("gateway.cli_unparsed_line", line=raw[:200])
            continue
        kind = event.get("type")
        if kind == "system" and event.get("subtype") == "init":
            _check_bridge(event)
        elif kind == "assistant":
            if event.get("error") == "authentication_failed":
                raise ProviderError(NOT_AUTHENTICATED, code="authentication")
            for block in (event.get("message") or {}).get("content") or []:
                if block.get("type") == "text" and block.get("text"):
                    yield TextDelta(text=block["text"])
                elif block.get("type") == "tool_use":
                    calls += 1
                    name = str(block.get("name", "")).removeprefix(TOOL_PREFIX)
                    yield ToolCallStart(id=block["id"], name=internal_tool_name(name))
                    yield ToolCallDelta(
                        id=block["id"], args_json_chunk=json.dumps(block.get("input") or {})
                    )
                    yield ToolCallEnd(id=block["id"])
        elif kind == "result":
            result = event
        else:
            logger.debug("gateway.cli_event_ignored", type=kind)
    if result is None:
        raise ProviderError("claude CLI exited without a result", retryable=True)
    yield _usage(result)
    yield Stop(reason=_stop_reason(result, calls))


def _check_bridge(event: dict[str, Any]) -> None:
    for server in event.get("mcp_servers") or []:
        if server.get("name") == MCP_SERVER and server.get("status") not in {"connected", None}:
            raise ProviderError(
                f"MCP bridge not connected: {server.get('status')}", code="configuration"
            )


def _stop_reason(result: dict[str, Any], calls: int) -> StopReason:
    subtype = result.get("subtype")
    text = str(result.get("result") or "")
    if result.get("is_error") and subtype == "success":
        if _AUTH_HINT.search(text):
            raise ProviderError(NOT_AUTHENTICATED, code="authentication")
        raise ProviderError(f"claude CLI error: {text[:500]}", retryable=True)
    if calls:
        return "tool_use"  # `error_max_turns` is expected after an intercepted tool call
    if subtype == "success":
        return "end"
    if subtype == "error_max_turns":
        return "max_tokens"
    raise ProviderError(f"claude CLI {subtype}: {text[:500]}", retryable=True)


def _usage(result: dict[str, Any]) -> Usage:
    usage = result.get("usage") or {}
    read = int(usage.get("cache_read_input_tokens") or 0)
    cost = result.get("total_cost_usd")
    return Usage(
        input=int(usage.get("input_tokens") or 0) + read,
        output=int(usage.get("output_tokens") or 0),
        cached_read=read,
        cached_write=int(usage.get("cache_creation_input_tokens") or 0),
        cost_usd=float(cost) if cost is not None else None,
    )


@contextlib.contextmanager
def cli_slot(limit: int, wait_s: float = 60.0) -> Iterator[None]:
    """At most `limit` CLI processes per worker host (CLI_MAX_CONCURRENT), shared via Redis."""
    from dexterhouse.apps.events.services.streams import get_client

    client = get_client()
    key = f"dh:gateway:cli_slots:{socket.gethostname()}"
    deadline = time.monotonic() + wait_s
    try:
        while client.incr(key) > limit:
            client.decr(key)
            if time.monotonic() > deadline:
                raise ProviderError(
                    "CLI_MAX_CONCURRENT reached", status="rate_limited", retryable=True
                )
            time.sleep(0.5)
        client.expire(key, get_gateway_env().CLI_TIMEOUT_S + 60)
    except redis.RedisError as exc:
        logger.warning("gateway.cli_slot_unavailable", error=str(exc))
        yield
        return
    try:
        yield
    finally:
        with contextlib.suppress(redis.RedisError):
            client.decr(key)
