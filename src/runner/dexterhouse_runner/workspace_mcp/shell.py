# SPDX-License-Identifier: AGPL-3.0-or-later
"""`workspace.exec`, `run_tests`, `services`, `open_port` (contracts/tools/workspace.md).

There is no allowlist of binaries: the defence is the container (non-root, no capabilities,
limits, internal network), not parsing the command. Each command runs in its own session
with `RLIMIT_FSIZE` at the workspace quota, without a TTY and with stdin closed, so an
interactive command ends at its timeout; on timeout the whole process group is killed.
"""

import os
import re
import resource
import signal
import socket
import subprocess  # nosec B404 - running the agent's commands is this server's job
import tempfile
import time
from typing import Any

from dexterhouse_runner.workspace_mcp.base import (
    ENV_ALLOWLIST,
    FULL_OUTPUT_LIMIT,
    Config,
    ToolFailure,
    clip,
    human,
    resolve,
    usage_bytes,
)

MAX_TIMEOUT_S = 900
#: Exit status of a process killed by SIGXFSZ (128 + 25): a file grew past the quota.
SIGXFSZ_EXIT = 128 + signal.SIGXFSZ
_FILE_TOO_LARGE = re.compile(r"file too large|no space left on device", re.IGNORECASE)
_PYTEST = {k: re.compile(rf"(\d+) {k}") for k in ("passed", "failed", "skipped", "error")}
_JEST = re.compile(r"^Tests:\s+(.*)$", re.MULTILINE)
_GO = {k: re.compile(rf"^\s*--- {k.upper()}", re.MULTILINE) for k in ("pass", "fail", "skip")}


def _base_env() -> dict[str, str]:
    """The container environment for the agent's commands, without the server's own venv."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("DH_")}
    venv = os.environ.get("VIRTUAL_ENV") or os.environ.get("DH_MCP_VENV", "/opt/dexterhouse")
    parts = [p for p in env.get("PATH", "").split(":") if p and not p.startswith(venv)]
    env["PATH"] = ":".join(parts) or "/usr/local/bin:/usr/bin:/bin"
    env.pop("VIRTUAL_ENV", None)
    env["HOME"] = env.get("HOME", "/home/dh")
    return env


def _env(cfg: Config, extra: dict[str, str] | None) -> dict[str, str]:
    env = _base_env()
    allowed = ENV_ALLOWLIST | cfg.stack_env_keys
    for key, value in (extra or {}).items():
        if key not in allowed:
            raise ToolFailure(
                "args_policy", f"env {key} is not allowed (allowed: {sorted(allowed)})"
            )
        env[key] = str(value)
    return env


def _limits(quota: int):
    def apply() -> None:  # runs in the child between fork and exec
        resource.setrlimit(resource.RLIMIT_FSIZE, (quota, quota))

    return apply


def run(
    cfg: Config,
    command: str,
    cwd: str = ".",
    timeout_s: int | None = None,
    env: dict[str, str] | None = None,
    *,
    check_quota: bool = True,
) -> dict[str, Any]:
    """Run `command` with `/bin/sh -c`; output goes to files so background jobs cannot hang it."""
    if not isinstance(command, str) or not command.strip():
        raise ToolFailure("invalid", "command is required")
    workdir = resolve(cfg.root, cwd)
    if not workdir.is_dir():
        raise ToolFailure("not_found", f"{cwd}: not a directory")
    timeout = min(max(int(timeout_s or cfg.exec_timeout_s), 1), MAX_TIMEOUT_S)
    started = time.monotonic()
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        process = subprocess.Popen(  # noqa: S603  # nosec B603 - see the module docstring
            ["/bin/sh", "-c", command],
            cwd=workdir,
            env=_env(cfg, env),
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            start_new_session=True,
            preexec_fn=_limits(cfg.quota_bytes),
        )
        timed_out = False
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_group(process.pid)
            code = process.wait()
        stdout, stderr = _read(out), _read(err)
    duration_ms = int((time.monotonic() - started) * 1000)
    result: dict[str, Any] = {"exit_code": code, "duration_ms": duration_ms}
    full: list[str] = []
    for name, text in (("stdout", stdout), ("stderr", stderr)):
        inline, cut = clip(text)
        result[name] = inline
        if cut:
            full.append(f"--- {name} ---\n{text[:FULL_OUTPUT_LIMIT]}")
    result["truncated"] = bool(full)
    if full:
        result["full_output"] = "\n".join(full)
    if timed_out:
        raise ToolFailure("timeout", f"command timed out after {timeout}s", **result)
    if code == SIGXFSZ_EXIT or (code != 0 and _FILE_TOO_LARGE.search(stderr[-2000:])):
        raise ToolFailure(
            "quota_exceeded",
            f"a file exceeded the workspace quota ({human(cfg.quota_bytes)})",
            **result,
        )
    if check_quota and usage_bytes(cfg.root) > cfg.quota_bytes:
        raise ToolFailure(
            "quota_exceeded",
            f"the workspace uses more than {human(cfg.quota_bytes)}: free some space",
            **result,
        )
    return result


def _kill_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _read(file: Any) -> str:
    file.seek(0)
    return file.read(FULL_OUTPUT_LIMIT + 1).decode("utf-8", errors="replace")


def narrow_test_command(cfg: Config, scope: str, path: str | None) -> str:
    """`stack.test_command`, narrowed to `path` for the framework it calls."""
    base = cfg.test_command
    if not base:
        raise ToolFailure("invalid", "the stack declares no test_command")
    if scope == "all" or not path:
        return base
    resolve(cfg.root, path)
    quoted = "'" + path.replace("'", "'\\''") + "'"
    if "go test" in base:
        return (
            re.sub(r"\./\.\.\.", f"./{path.rstrip('/')}/...", base)
            if "./..." in base
            else (f"{base} ./{path.rstrip('/')}/...")
        )
    if any(word in base for word in ("jest", "vitest", "npm", "pnpm", "yarn")):
        return (
            f"{base} -- {quoted}"
            if base.split()[0] in ("npm", "pnpm", "yarn")
            else (f"{base} {quoted}")
        )
    return f"{base} {quoted}"


def summarize(output: str) -> dict[str, int]:
    """Passed/failed/skipped parsed from pytest, jest/vitest or `go test -v` output."""
    if match := _JEST.search(output):
        counts = dict.fromkeys(("passed", "failed", "skipped"), 0)
        for number, word in re.findall(r"(\d+) (passed|failed|skipped|todo)", match[1]):
            key = "skipped" if word == "todo" else word
            counts[key] += int(number)
        return counts
    if _GO["pass"].search(output) or _GO["fail"].search(output):
        return {
            "passed": len(_GO["pass"].findall(output)),
            "failed": len(_GO["fail"].findall(output)),
            "skipped": len(_GO["skip"].findall(output)),
        }
    found = {k: sum(int(n) for n in r.findall(output)) for k, r in _PYTEST.items()}
    return {
        "passed": found["passed"],
        "failed": found["failed"] + found["error"],
        "skipped": found["skipped"],
    }


def run_tests(
    cfg: Config, scope: str = "all", path: str | None = None, timeout_s: int | None = None
) -> dict:
    if scope not in ("all", "path"):
        raise ToolFailure("invalid", "scope must be `all` or `path`")
    command = narrow_test_command(cfg, scope, path)
    try:
        result = run(cfg, command, timeout_s=timeout_s or cfg.test_timeout_s)
    except ToolFailure as exc:
        if exc.code != "timeout":
            raise
        result = {**exc.data, "timed_out": True}
    output = f"{result.get('stdout', '')}\n{result.get('stderr', '')}"
    full = result.get("full_output") or output
    summary = summarize(full)
    ok = result.get("exit_code") == 0 and not result.get("timed_out")
    return {
        **result,
        "command": command,
        "summary": summary,
        "ok": ok,
        "full_output": f"$ {command}\n{full}"[:FULL_OUTPUT_LIMIT],
    }


def services(cfg: Config) -> dict:
    """The stack's sidecars and whether their port answers."""
    listed = []
    for service in cfg.services:
        up = False
        try:
            with socket.create_connection((service["host"], int(service["port"])), timeout=2):
                up = True
        except OSError:
            up = False
        listed.append({**service, "status": "up" if up else "down"})
    return {"services": listed}


def open_port(cfg: Config, port: int) -> dict:
    if not isinstance(port, int) or not 1024 <= port <= 65535:
        raise ToolFailure("invalid", "port must be between 1024 and 65535")
    return {
        "port": port,
        "url": f"http://127.0.0.1:{port}",
        "note": "reachable from workspace.exec only; never exposed outside the sandbox",
    }
