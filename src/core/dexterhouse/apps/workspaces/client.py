# SPDX-License-Identifier: AGPL-3.0-or-later
"""The core's side of the runner protocol (infra/runner_protocol.md).

`CeleryRunnerClient` sends `dexterhouse_schema.runner` messages to the `runner` queue and
waits for the `ToolResult` through the result backend, with the protocol's timeouts; a
missing heartbeat (runner down, 45 s) answers `workspace_not_ready` at once instead of
waiting. `LocalRunnerClient` stands in when no runner exists (unit tests, engine-only
development): workspaces are ready at once and system actions succeed without running
anything, the E-02 no-op behaviour. `settings.RUNNER_CLIENT` picks one.
"""

import hashlib
import json
from typing import Any, Protocol

import redis
import structlog
from celery.exceptions import TimeoutError as CeleryTimeout
from django.conf import settings
from django.db import transaction
from django.utils.module_loading import import_string

from dexterhouse.celery import app as celery_app
from dexterhouse_schema.runner import RUNNER_QUEUE, Message, ToolResult, WorkspaceChanged

logger = structlog.get_logger(__name__)

HEARTBEAT_KEY = "runner:heartbeat:"
HEARTBEAT_TTL_S = 45
#: Seconds the core waits for each task beyond the work itself (queue, Docker, MCP).
TIMEOUTS_S = {
    "runner.workspace.status": 10,
    "runner.workspace.destroy": 60,
    "runner.tool.list": 60,
    "runner.system.branch_create": 30,
    "runner.system.merge": 60,
    "runner.system.deliver": 180,
    "runner.system.commit_log": 30,
    "runner.system.tree": 30,
    "runner.system.code_graph": 120,
    "runner.system.ls_tree": 20,
    "runner.system.read_file": 20,
}
GRACE_S = 15


class RunnerClient(Protocol):
    inline: bool

    def call(self, task: str, message: Message, timeout_s: float | None = None) -> ToolResult: ...

    def send(self, task: str, message: Message) -> WorkspaceChanged | None:
        """Fire and forget; a client with no runner returns the reply it would have sent."""
        ...


def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL, socket_timeout=2)


def runner_heartbeats() -> dict[str, dict[str, Any]]:
    """Live runners (`runner:heartbeat:<id>` written by the heartbeat callback)."""
    try:
        client = _redis()
        keys = list(client.scan_iter(f"{HEARTBEAT_KEY}*"))
        values = client.mget(keys) if keys else []
    except redis.RedisError as exc:
        logger.warning("workspaces.heartbeat_read_failed", error=str(exc))
        return {}
    return {
        k.decode().removeprefix(HEARTBEAT_KEY): json.loads(v)
        for k, v in zip(keys, values, strict=True)
        if v
    }


class CeleryRunnerClient:
    inline = False

    def call(self, task: str, message: Message, timeout_s: float | None = None) -> ToolResult:
        if not runner_heartbeats():
            return ToolResult.failure("workspace_not_ready", "the runner is down (no heartbeat)")
        wait = (timeout_s if timeout_s is not None else TIMEOUTS_S.get(task, 60)) + GRACE_S
        try:
            result = celery_app.send_task(task, args=[message.dump()], queue=RUNNER_QUEUE)
            payload = result.get(timeout=wait, disable_sync_subtasks=False, propagate=True)
        except CeleryTimeout:
            return ToolResult.failure(
                "timeout", f"{task}: no answer from the runner in {wait:.0f}s"
            )
        except Exception as exc:  # broker down or the runner task crashed
            logger.warning("workspaces.runner_call_failed", task=task, error=str(exc))
            return ToolResult.failure("internal", f"{task}: {exc}")
        return ToolResult.model_validate(payload)

    def send(self, task: str, message: Message) -> None:
        """Fire and forget, after the caller's transaction commits (the callback needs the row)."""
        args = [message.dump()]
        transaction.on_commit(
            lambda: celery_app.send_task(task, args=args, queue=RUNNER_QUEUE), robust=True
        )
        return None


def _fake_commit(*parts: object) -> str:
    return hashlib.sha1(":".join(map(str, parts)).encode(), usedforsecurity=False).hexdigest()


class LocalRunnerClient:
    """No runner: answers like one that executes nothing (tests, engine-only setups)."""

    inline = True

    def call(self, task: str, message: Message, timeout_s: float | None = None) -> ToolResult:
        data: dict[str, Any] = {}
        if task == "runner.system.merge":
            data = {
                "commit": _fake_commit(message.task_id, message.branch),  # type: ignore[attr-defined]
                "files_changed": 0,
                "insertions": 0,
                "deletions": 0,
            }
        elif task == "runner.system.deliver":
            data = {
                "commit": _fake_commit(message.workspace_id, message.remote_url),  # type: ignore[attr-defined]
                "branch": message.branch_name,
                "pr_url": None,
            }  # type: ignore[attr-defined]
        elif task == "runner.system.exit_check":
            data = {
                "summary": {"passed": 0, "failed": 0, "skipped": 0},
                "detail": "not executed: no runner",
            }
        elif task == "runner.system.commit_log":
            data = {"commits": []}
        elif task in (
            "runner.tool.invoke",
            "runner.tool.list",
            "runner.system.tree",
            "runner.system.code_graph",
            "runner.system.ls_tree",
            "runner.system.read_file",
        ):
            return ToolResult.failure("workspace_not_ready", "no runner in this setup")
        return ToolResult(
            ok=True, exit_code=0 if task == "runner.system.exit_check" else None, data=data
        )

    def send(self, task: str, message: Message) -> WorkspaceChanged | None:
        """The reply a runner would send back; the caller applies it (`services.apply_changed`)."""
        if task == "runner.workspace.create":
            return WorkspaceChanged(
                workspace_id=message.workspace_id,  # type: ignore[attr-defined]
                status="ready",
                image=str(message.stack.get("workspace_image", "")),  # type: ignore[attr-defined]
                digest="sha256:" + "0" * 64,
                services=[str(s) for s in message.stack.get("services") or []],  # type: ignore[attr-defined]
            )
        if task == "runner.workspace.destroy":
            return WorkspaceChanged(workspace_id=message.workspace_id, status="destroyed")  # type: ignore[attr-defined]
        return None


def get_client() -> RunnerClient:
    return import_string(settings.RUNNER_CLIENT)()
