# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the runner does for each message of the `runner` queue (infra/runner_protocol.md).

`RunnerService` is plain Python over a `DockerManager`, a `SessionPool`, the callbacks and a
Redis client, so the unit tests run it with fakes. The Celery tasks (`tasks.py`) only
validate the payload and call it. System git operations run as uid 1000 inside the
container; tool calls go through the workspace's MCP session, one at a time per workspace
(CD-038), and their results are cached for an hour under `turn_id:seq` (idempotency).
"""

import json
import re
import shlex
import time
import uuid
from typing import Any

import structlog
from docker.errors import DockerException

from dexterhouse_runner import __version__, metrics
from dexterhouse_runner.callbacks import Callbacks
from dexterhouse_runner.config import RunnerSettings
from dexterhouse_runner.delivery import Delivery
from dexterhouse_runner.docker_manager import DockerManager, RunnerError, image_ref, quota
from dexterhouse_runner.grants import redeem
from dexterhouse_runner.sessions import BUILTIN, SessionError, SessionPool
from dexterhouse_runner.workspace_mcp.shell import summarize
from dexterhouse_schema.runner import (
    BranchCreate,
    CodeGraph,
    CommitLog,
    Deliver,
    ExitCheck,
    Heartbeat,
    Merge,
    SecretsBlocked,
    ServerSpec,
    ToolError,
    ToolInvoke,
    ToolList,
    ToolResult,
    Tree,
    WorkspaceChanged,
    WorkspaceCreate,
    WorkspaceDestroy,
    WorkspaceStatusQuery,
)

logger = structlog.get_logger(__name__)

RESULT_TTL_S = 3600
MAX_THIRD_PARTY = 3
THIRD_PARTY_LAUNCHERS = frozenset({"uvx", "npx", "python", "node"})
GIT_ENV = {
    "GIT_COMMITTER_NAME": "DexterHouse",
    "GIT_COMMITTER_EMAIL": "noreply@dexterhouse.dev",
    "GIT_AUTHOR_NAME": "DexterHouse",
    "GIT_AUTHOR_EMAIL": "noreply@dexterhouse.dev",
    "GIT_TERMINAL_PROMPT": "0",
}
_ENV_KEY = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_RESERVED_ENV = re.compile(r"^(DH_|HTTPS?_PROXY$|NO_PROXY$|HOME$|PATH$)", re.IGNORECASE)
_SHORTSTAT = re.compile(
    r"(\d+) files? changed(?:, (\d+) insertions?\(\+\))?(?:, (\d+) deletions?\(-\))?"
)
PRE_COMMIT_HOOK = """#!/bin/sh
# DexterHouse: detect-secrets on every commit, also the ones made with workspace.exec.
git diff --cached --name-only -z --diff-filter=ACMR | xargs -0 -r detect-secrets-hook
"""
_PROBE = """
import os, signal, subprocess, sys, time, urllib.error, urllib.request
command, url, wait = sys.argv[1], sys.argv[2], int(sys.argv[3])
log = open("/tmp/dh-smoke.log", "wb")
proc = subprocess.Popen(["/bin/sh", "-c", command], stdout=log, stderr=subprocess.STDOUT,
                        start_new_session=True)
ok = False
for _ in range(wait):
    if proc.poll() is not None:
        break
    try:
        urllib.request.urlopen(url, timeout=2)
        ok = True
    except urllib.error.HTTPError as exc:
        ok = exc.code < 500
    except Exception:
        time.sleep(1)
        continue
    break
try:
    os.killpg(proc.pid, signal.SIGTERM)
except ProcessLookupError:
    pass
log.close()
print(("probe ok: " if ok else "probe failed: ") + url)
print(open("/tmp/dh-smoke.log", errors="replace").read()[-8000:])
sys.exit(0 if ok else 1)
"""

#: Task name -> `RunnerService` method (also used by in-process test clients).
TASK_METHODS = {
    "runner.workspace.create": "create",
    "runner.workspace.destroy": "destroy",
    "runner.workspace.status": "status",
    "runner.tool.invoke": "invoke",
    "runner.tool.list": "list_tools",
    "runner.system.branch_create": "branch_create",
    "runner.system.merge": "merge",
    "runner.system.deliver": "deliver",
    "runner.system.exit_check": "exit_check",
    "runner.system.commit_log": "commit_log",
    "runner.system.tree": "tree",
    "runner.system.code_graph": "code_graph",
}


class RunnerService:
    def __init__(
        self,
        settings: RunnerSettings,
        docker: DockerManager,
        pool: SessionPool,
        callbacks: Callbacks,
        redis: Any,
    ) -> None:
        self.settings = settings
        self.docker = docker
        self.pool = pool
        self.callbacks = callbacks
        self.redis = redis
        self._egress_since = int(time.time())
        self._egress_last = ""  # RFC 3339 timestamp of the last proxy log line counted

    # Workspace lifecycle ------------------------------------------------------------------

    def _changed(self, ws: uuid.UUID, status: str, **fields: Any) -> WorkspaceChanged:
        message = WorkspaceChanged(workspace_id=ws, status=status, **fields)  # type: ignore[arg-type]
        self.callbacks.workspace_changed(message)
        return message

    def _ready(self, ws: uuid.UUID, container: Any) -> WorkspaceChanged:
        labels = container.labels or {}
        services = [
            c.labels.get("dexterhouse.service", "")
            for c in self.docker.client.containers.list(
                filters={"label": [f"dexterhouse.workspace={ws}", "dexterhouse.role=sidecar"]}
            )
        ]
        return self._changed(
            ws,
            "ready",
            image=labels.get("dexterhouse.image", ""),
            digest=container.image.id,
            container_id=container.id,
            services=sorted(s for s in services if s),
        )

    def create(self, msg: WorkspaceCreate) -> ToolResult:
        ws = msg.workspace_id
        existing = self.docker.find(ws)
        if existing is not None and existing.status == "running":
            return ToolResult(ok=True, data=self._ready(ws, existing).dump())
        if existing is not None:
            try:  # a stopped container keeps its volume: restart it rather than lose the code
                existing.start()
                existing.reload()
                if existing.status == "running":
                    return ToolResult(ok=True, data=self._ready(ws, existing).dump())
            except DockerException as exc:
                logger.warning(
                    "runner.workspace_restart_failed", workspace_id=str(ws), error=str(exc)
                )
            self.docker.destroy(ws)
        try:
            image = image_ref(str(msg.stack.get("workspace_image", "")), self.settings)
        except RunnerError as exc:
            self._changed(
                ws,
                "error",
                image=str(msg.stack.get("workspace_image", "")),
                error_detail=exc.detail,
            )
            return ToolResult.failure(exc.code, exc.detail)
        self._changed(ws, "creating", image=image)
        try:
            services = [str(s) for s in msg.stack.get("services") or []]
            created = self.docker.create(
                ws, msg.project_id, image, self._workspace_env(msg, services), services, msg.limits
            )
            self._init_repo(ws)
            self.pool.list_tools(str(ws), BUILTIN, self._spec(ws))
        except (RunnerError, DockerException, SessionError, TimeoutError) as exc:
            detail = getattr(exc, "detail", None) or str(exc)
            logger.warning("runner.workspace_create_failed", workspace_id=str(ws), error=detail)
            self.pool.close_workspace(str(ws))
            self.docker.destroy(ws)
            self._changed(ws, "error", image=image, error_detail=detail[:2000])
            return ToolResult.failure("workspace_not_ready", detail)
        metrics.WORKSPACES.set(len(self.docker.managed()))
        container = self.docker.running(ws)
        logger.info(
            "runner.workspace_ready", workspace_id=str(ws), image=image, digest=created.digest
        )
        return ToolResult(ok=True, data=self._ready(ws, container).dump())

    def _workspace_env(self, msg: WorkspaceCreate, services: list[str]) -> dict[str, str]:
        stack = msg.stack
        stack_env = {
            str(k): str(v)
            for k, v in (stack.get("env") or {}).items()
            if _ENV_KEY.match(str(k)) and not _RESERVED_ENV.match(str(k))
        }
        return {
            **stack_env,
            "DH_WORKSPACE_ROOT": "/workspace",
            "DH_WORKSPACE_QUOTA": quota(msg.limits),
            "DH_TEST_COMMAND": str(stack.get("test_command") or ""),
            "DH_LINT_COMMAND": str(stack.get("lint_command") or ""),
            "DH_STACK_ENV_KEYS": ",".join(sorted(stack_env)),
            "DH_SERVICES": json.dumps(self.docker.services_spec(services)),
            "DH_EXEC_TIMEOUT_S": str(msg.limits.exec_timeout_s),
            "DH_TEST_TIMEOUT_S": str(msg.limits.test_timeout_s),
        }

    def _init_repo(self, ws: uuid.UUID) -> None:
        script = (
            "set -e; [ -d .git ] || git init -q -b main; "
            "git config user.name DexterHouse; git config user.email noreply@dexterhouse.dev; "
            "git config credential.helper ''; git config commit.gpgsign false; "
            f"printf '%s' {shlex.quote(PRE_COMMIT_HOOK)} > .git/hooks/pre-commit; "
            "chmod 755 .git/hooks/pre-commit; "
            "git rev-parse -q --verify HEAD >/dev/null || "
            "git commit -q --allow-empty --no-verify -m 'chore: initial commit'"
        )
        code, out, err = self.docker.exec(ws, ["/bin/sh", "-c", script], env=GIT_ENV)
        if code != 0:
            raise RunnerError("workspace_not_ready", f"git init failed: {(err or out)[-500:]}")

    def destroy(self, msg: WorkspaceDestroy) -> ToolResult:
        self.pool.close_workspace(str(msg.workspace_id))
        self.docker.destroy(msg.workspace_id)
        metrics.WORKSPACES.set(len(self.docker.managed()))
        self._changed(msg.workspace_id, "destroyed")
        return ToolResult(ok=True, data={"reason": msg.reason})

    def status(self, msg: WorkspaceStatusQuery) -> ToolResult:
        container = self.docker.find(msg.workspace_id)
        if container is None:
            status = "destroyed"
        else:
            status = "ready" if container.status == "running" else "error"
        data = WorkspaceChanged(
            workspace_id=msg.workspace_id,
            status=status,  # type: ignore[arg-type]
            container_id=container.id if container is not None else None,
        )
        return ToolResult(ok=status == "ready", data=data.dump())

    # Tools --------------------------------------------------------------------------------

    def _spec(self, ws: uuid.UUID, server: ServerSpec | None = None) -> Any:
        if server is None:
            return self.pool.spec(self.docker.name(ws), [self.settings.WORKSPACE_MCP_COMMAND])
        return self.pool.spec(self.docker.name(ws), server.command, server.env)

    def _server(self, ws: uuid.UUID, server: ServerSpec | None) -> tuple[str, Any]:
        if server is None:
            return BUILTIN, self._spec(ws)
        if not server.command or server.command[0] not in THIRD_PARTY_LAUNCHERS:
            raise RunnerError(
                "tool_unknown",
                f"{server.name}: command[0] must be one of "
                f"{sorted(THIRD_PARTY_LAUNCHERS)} inside a workspace",
            )
        key = f"tool:{server.name}"
        if (
            not self.pool.has(str(ws), key)
            and self.pool.third_party_count(str(ws)) >= MAX_THIRD_PARTY
        ):
            raise RunnerError(
                "quota_exceeded", f"at most {MAX_THIRD_PARTY} tool servers per workspace"
            )
        return key, self._spec(ws, server)

    def list_tools(self, msg: ToolList) -> ToolResult:
        try:
            self.docker.running(msg.workspace_id)
            name, spec = self._server(msg.workspace_id, msg.server)
            listed = self.pool.list_tools(str(msg.workspace_id), name, spec)
        except RunnerError as exc:
            return ToolResult.failure(exc.code, exc.detail)
        except (SessionError, TimeoutError) as exc:
            return ToolResult.failure("internal", str(exc))
        tools = []
        for tool in listed:
            schema = json.loads(json.dumps(tool.input_schema))
            if msg.server is None and tool.name == "git_commit":
                schema.get("properties", {}).pop("author", None)  # set by the runner per call
            tools.append(
                {"name": tool.name, "description": tool.description, "input_schema": schema}
            )
        return ToolResult(ok=True, data={"tools": tools})

    def invoke(self, msg: ToolInvoke) -> ToolResult:
        cache_key = f"runner:result:{msg.turn_id}:{msg.seq}"
        cached = self.redis.get(cache_key)
        if cached:
            return ToolResult.model_validate_json(cached)
        started = time.monotonic()
        result = self._invoke(msg)
        result.duration_ms = int((time.monotonic() - started) * 1000)
        status = "ok" if result.ok else (result.error.code if result.error else "error")
        metrics.EXECS.labels(tool=msg.tool, status=status).inc()
        metrics.EXEC_SECONDS.observe(result.duration_ms / 1000)
        if result.error is not None:
            metrics.ERRORS.labels(code=result.error.code).inc()
        if result.error is None or result.error.code not in (
            "timeout",
            "internal",
            "workspace_not_ready",
        ):
            self.redis.set(cache_key, result.model_dump_json(by_alias=True), ex=RESULT_TTL_S)
        return result

    def _invoke(self, msg: ToolInvoke) -> ToolResult:
        ws = msg.workspace_id
        try:
            self.docker.running(ws)
            name, spec = self._server(ws, msg.server)
        except RunnerError as exc:
            return ToolResult.failure(exc.code, exc.detail)
        args = dict(msg.args)
        if msg.server is None and msg.tool == "git_commit":
            args["author"] = msg.agent_display_name
        timeout = max(msg.timeout_s, 1)
        lock = self.redis.lock(
            f"runner:ws:lock:{ws}", timeout=timeout + 60, blocking_timeout=timeout + 10
        )
        if not lock.acquire():
            return ToolResult.failure("timeout", "the workspace is busy with another command")
        try:
            data = self.pool.call(str(ws), name, spec, msg.tool, args, timeout + 10)
        except TimeoutError as exc:
            return ToolResult.failure("timeout", str(exc))
        except SessionError as exc:
            if exc.broken:  # the container may be fine: never recreate it (the code is there)
                logger.error("runner.mcp_server_broken", workspace_id=str(ws), error=str(exc))
            return ToolResult.failure("internal", str(exc))
        finally:
            try:
                lock.release()
            except Exception:  # the lock expired: nothing to release
                logger.warning("runner.lock_expired", workspace_id=str(ws))
        result = to_result(data)
        if result.error is not None and result.error.code == "secrets_blocked":
            files = [str(f) for f in data.get("files", [])]
            self.callbacks.secrets_blocked(
                SecretsBlocked(
                    workspace_id=ws,
                    turn_id=msg.turn_id,
                    files=files,
                    count=int(data.get("count", len(files))),
                )
            )
        return result

    def _tool(
        self, ws: uuid.UUID, tool: str, args: dict[str, Any], timeout_s: int
    ) -> dict[str, Any]:
        """A system call of a built-in tool (merge leftovers, exit checks, tree)."""
        try:
            return self.pool.call(str(ws), BUILTIN, self._spec(ws), tool, args, timeout_s + 10)
        except TimeoutError as exc:
            raise RunnerError("timeout", str(exc)) from exc
        except SessionError as exc:
            raise RunnerError("internal", str(exc)) from exc

    # System actions -----------------------------------------------------------------------

    def _git(self, ws: uuid.UUID, *args: str, check: bool = True) -> str:
        code, out, err = self.docker.exec(ws, ["git", *args], env=GIT_ENV)
        if check and code != 0:
            raise RunnerError("conflict", f"git {args[0]}: {(err or out).strip()[-1000:]}")
        return out

    def _system(self, action: str, call: Any) -> ToolResult:
        started = time.monotonic()
        try:
            result = call()
        except RunnerError as exc:
            result = ToolResult.failure(exc.code, exc.detail)
        except DockerException as exc:
            result = ToolResult.failure("internal", str(exc))
        result.duration_ms = int((time.monotonic() - started) * 1000)
        metrics.SYSTEM.labels(action=action, status="ok" if result.ok else "error").inc()
        if result.error is not None:
            metrics.ERRORS.labels(code=result.error.code).inc()
        return result

    def branch_create(self, msg: BranchCreate) -> ToolResult:
        def run() -> ToolResult:
            self.docker.running(msg.workspace_id)
            exists = self._git(
                msg.workspace_id,
                "rev-parse",
                "-q",
                "--verify",
                f"refs/heads/{msg.branch}",
                check=False,
            ).strip()
            if exists:
                self._git(msg.workspace_id, "checkout", "-q", msg.branch)
            else:
                self._git(msg.workspace_id, "checkout", "-q", "-b", msg.branch, msg.from_)
            return ToolResult(ok=True, data={"branch": msg.branch, "existed": bool(exists)})

        return self._system("branch_create", run)

    def merge(self, msg: Merge) -> ToolResult:
        def run() -> ToolResult:
            ws = msg.workspace_id
            self.docker.running(ws)
            if not self._git(
                ws, "rev-parse", "-q", "--verify", f"refs/heads/{msg.branch}", check=False
            ).strip():
                raise RunnerError("conflict", f"branch {msg.branch} does not exist")
            current = self._git(ws, "rev-parse", "--abbrev-ref", "HEAD").strip()
            if self._git(ws, "status", "--porcelain").strip() and current == msg.branch:
                scope = msg.branch.split("/")[-1]
                left = self._tool(
                    ws,
                    "git_commit",
                    {
                        "message": f"chore({scope}): commit pending changes",
                        "all": True,
                        "author": "DexterHouse",
                    },
                    120,
                )
                if "error" in left:
                    raise RunnerError(left["error"]["code"], left["error"]["detail"])
            code, _, _ = self.docker.exec(
                ws, ["git", "merge-base", "--is-ancestor", msg.branch, "main"]
            )
            self._git(ws, "checkout", "-q", "main")
            if code == 0:
                head = self._git(ws, "rev-parse", "HEAD").strip()
                return ToolResult(
                    ok=True,
                    data={
                        "commit": head,
                        "already": True,
                        "files_changed": 0,
                        "insertions": 0,
                        "deletions": 0,
                    },
                )
            code, out, err = self.docker.exec(
                ws,
                ["git", "merge", "--no-ff", "--no-edit", "-m", msg.message, msg.branch],
                env=GIT_ENV,
            )
            if code != 0:
                self.docker.exec(ws, ["git", "merge", "--abort"])
                raise RunnerError(
                    "conflict", f"merge of {msg.branch} failed: {(out + err)[-1000:]}"
                )
            head = self._git(ws, "rev-parse", "HEAD").strip()
            return ToolResult(
                ok=True,
                data={
                    "commit": head,
                    **shortstat(self._git(ws, "diff", "--shortstat", "HEAD^1", "HEAD")),
                },
            )

        return self._system("merge", run)

    def exit_check(self, msg: ExitCheck) -> ToolResult:
        def run() -> ToolResult:
            self.docker.running(msg.workspace_id)
            command = msg.command
            if msg.probe_url:
                wait = int(max(min(msg.timeout_s - 5, 60), 5))
                command = "python3 -c " + " ".join(
                    shlex.quote(a) for a in (_PROBE, msg.command, msg.probe_url, str(wait))
                )
            data = self._tool(
                msg.workspace_id,
                "workspace_exec",
                {"command": command, "timeout_s": msg.timeout_s},
                msg.timeout_s,
            )
            error = data.pop("error", None)
            full = data.pop("full_output", None)
            output = full or f"{data.get('stdout', '')}\n{data.get('stderr', '')}"
            if error is not None and error["code"] not in ("timeout", "quota_exceeded"):
                raise RunnerError(error["code"], error["detail"])
            exit_code = data.get("exit_code")
            ok = error is None and exit_code == 0
            return ToolResult(
                ok=ok,
                exit_code=exit_code,
                data={
                    "summary": summarize(output),
                    "command": msg.command,
                    "detail": error["detail"] if error else None,
                    "tail": output[-4000:],
                },
                artifact_payload=f"$ {msg.command}\n{output}",
            )

        return self._system("exit_check", run)

    def commit_log(self, msg: CommitLog) -> ToolResult:
        def run() -> ToolResult:
            self.docker.running(msg.workspace_id)
            out = self._git(
                msg.workspace_id,
                "log",
                f"--max-count={min(msg.max, 500)}",
                "--format=%H%x1f%an%x1f%aI%x1f%s",
                msg.ref,
            )
            commits = []
            for line in out.splitlines():
                sha, author, date, subject = [*line.split("\x1f"), "", "", ""][:4]
                commits.append({"commit": sha, "author": author, "date": date, "message": subject})
            return ToolResult(ok=True, data={"commits": commits})

        return self._system("commit_log", run)

    def tree(self, msg: Tree) -> ToolResult:
        def run() -> ToolResult:
            self.docker.running(msg.workspace_id)
            data = self._tool(msg.workspace_id, "workspace_list", {"depth": msg.depth}, 30)
            if "error" in data:
                raise RunnerError(data["error"]["code"], data["error"]["detail"])
            return ToolResult(
                ok=True, data={"tree": data.get("tree", ""), "truncated": data.get("truncated")}
            )

        return self._system("tree", run)

    def code_graph(self, msg: CodeGraph) -> ToolResult:
        def run() -> ToolResult:
            self.docker.running(msg.workspace_id)
            args = {"include_graph": msg.include_graph, "summary_chars": msg.summary_chars}
            data = self._tool(msg.workspace_id, "workspace_graph_export", args, 120)
            if "error" in data:
                raise RunnerError(data["error"]["code"], data["error"]["detail"])
            return ToolResult(ok=True, data=data)

        return self._system("code_graph", run)

    def deliver(self, msg: Deliver) -> ToolResult:
        def run() -> ToolResult:
            self.docker.running(msg.workspace_id)
            token = redeem(msg.token_ref, self.settings) if msg.token_ref else None
            try:
                stream = self.docker.archive(msg.workspace_id, "/workspace/.git")
                delivered = Delivery(stream, msg.remote_url, token).push(
                    msg.mode,
                    msg.branch_name,
                    msg.base,
                    msg.pr.model_dump() if msg.pr is not None else None,
                )
            finally:
                token = None
            return ToolResult(
                ok=True,
                data={
                    "commit": delivered.commit,
                    "branch": delivered.branch,
                    "pr_url": delivered.pr_url,
                    "already": delivered.already,
                },
            )

        return self._system("deliver", run)

    # Heartbeat ----------------------------------------------------------------------------

    def heartbeat(self) -> Heartbeat:
        managed = self.docker.managed()
        metrics.WORKSPACES.set(len(managed))
        self._count_egress_denied()
        self.pool.close_idle()
        message = Heartbeat(
            runner_id=self.settings.RUNNER_ID,
            version=__version__,
            active_workspaces=sum(1 for s in managed.values() if s == "running"),
            metrics=metrics.snapshot(),
            workspaces=[uuid.UUID(w) for w in managed],
        )
        self.callbacks.heartbeat(message)
        return message

    def _count_egress_denied(self) -> None:
        """Count the proxy's `TCP_DENIED` lines logged since the previous heartbeat."""
        proxy = self.docker.proxy()
        if proxy is None:
            return
        try:
            logs = proxy.logs(since=self._egress_since, stdout=True, stderr=True, timestamps=True)
        except DockerException as exc:
            logger.warning("runner.proxy_logs_failed", error=str(exc))
            return
        denied = 0
        for line in logs.decode("utf-8", errors="replace").splitlines():
            stamp, _, text = line.partition(" ")
            if stamp > self._egress_last:
                self._egress_last = stamp
                denied += "TCP_DENIED" in text
        self._egress_since = max(int(time.time()) - 1, self._egress_since)
        if denied:
            metrics.EGRESS_DENIED.inc(denied)


def to_result(data: dict[str, Any]) -> ToolResult:
    """The server's JSON object -> `ToolResult` (full output past 64 KB as `artifact_payload`)."""
    data = dict(data)
    error = data.pop("error", None)
    full = data.pop("full_output", None)
    return ToolResult(
        ok=error is None,
        exit_code=data.get("exit_code") if isinstance(data.get("exit_code"), int) else None,
        data=data,
        truncated=bool(data.get("truncated")),
        artifact_payload=full,
        error=ToolError(
            code=error.get("code", "internal"), detail=str(error.get("detail", ""))[:2000]
        )
        if isinstance(error, dict)
        else None,
    )


def shortstat(text: str) -> dict[str, int]:
    match = _SHORTSTAT.search(text)
    if not match:
        return {"files_changed": 0, "insertions": 0, "deletions": 0}
    return {
        "files_changed": int(match[1]),
        "insertions": int(match[2] or 0),
        "deletions": int(match[3] or 0),
    }
