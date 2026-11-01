# SPDX-License-Identifier: AGPL-3.0-or-later
"""Runner tests: the workspace tools on a temporary directory, the service with fakes.

Short `git` and `/bin/sh` subprocesses (milliseconds) stay in the fast suite; tests that
start an MCP server, detect-secrets, a Celery worker or Docker are marked `slow`/`security`.
"""

import subprocess
from pathlib import Path

import pytest

from dexterhouse_runner.workspace_mcp.base import Config


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "commit", "-q", "--allow-empty", "-m", "chore: initial commit")
    return root


@pytest.fixture
def cfg(repo: Path) -> Config:
    return Config(
        root=repo, quota_bytes=50 * 1024 * 1024, test_command="python3 -c 'print(\"1 passed\")'"
    )


# Fakes for RunnerService: "containers" are directories, exec runs locally ----------------

import io  # noqa: E402
import tarfile  # noqa: E402
import uuid  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from typing import Any  # noqa: E402

from dexterhouse_runner.config import RunnerSettings  # noqa: E402
from dexterhouse_runner.docker_manager import Created, DockerManager, RunnerError  # noqa: E402
from dexterhouse_runner.service import RunnerService  # noqa: E402
from dexterhouse_runner.sessions import Listed, SessionError  # noqa: E402
from dexterhouse_runner.workspace_mcp import server as mcp_server  # noqa: E402


class FakeDocker(DockerManager):
    def __init__(self, settings: RunnerSettings, base: Path) -> None:
        self.settings = settings
        self.base = base
        self.containers: dict[str, SimpleNamespace] = {}
        self.destroyed: list[str] = []
        self.fail_create: Exception | None = None
        self.client = SimpleNamespace(containers=SimpleNamespace(list=lambda **_: []))
        self.proxy_logs = b""

    def root(self, ws: Any) -> Path:
        return self.base / str(ws)

    def find(self, workspace_id: Any) -> Any:
        return self.containers.get(str(workspace_id))

    def create(self, workspace_id, project_id, image, env, services, limits) -> Created:
        if self.fail_create is not None:
            raise self.fail_create
        self.root(workspace_id).mkdir(parents=True, exist_ok=True)
        self.containers[str(workspace_id)] = SimpleNamespace(
            id=f"c-{workspace_id}",
            status="running",
            env=env,
            labels={"dexterhouse.image": image},
            image=SimpleNamespace(id="sha256:" + "a" * 64),
        )
        return Created(f"c-{workspace_id}", image, "sha256:" + "a" * 64, services)

    def destroy(self, workspace_id: Any) -> None:
        self.destroyed.append(str(workspace_id))
        self.containers.pop(str(workspace_id), None)

    def managed(self) -> dict[str, str]:
        return {k: c.status for k, c in self.containers.items()}

    def exec(self, workspace_id, argv, env=None, workdir="/workspace"):
        self.running(workspace_id)
        done = subprocess.run(
            argv,
            cwd=self.root(workspace_id),
            env={**__import__("os").environ, **(env or {})},
            capture_output=True,
            text=True,
            check=False,
        )
        return done.returncode, done.stdout, done.stderr

    def archive(self, workspace_id: Any, path: str) -> Any:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as tar:
            tar.add(self.root(workspace_id) / ".git", arcname=".git")
        return iter([buffer.getvalue()])

    def proxy(self) -> Any:
        return SimpleNamespace(logs=lambda **_: self.proxy_logs)


class FakePool:
    """Calls the workspace tools in-process on the fake container's directory."""

    def __init__(self, docker: FakeDocker) -> None:
        self.docker = docker
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail: Exception | None = None
        self.closed: list[str] = []
        self.servers: set[tuple[str, str]] = set()

    def spec(self, container: str, command: list[str], env: dict[str, str] | None = None) -> Any:
        return SimpleNamespace(container=container, command=command, env=env)

    def _tools(self, ws: str) -> dict[str, Any]:
        container = self.docker.containers[ws]
        cfg = mcp_server.Config.from_env({**container.env})
        cfg = mcp_server.Config(**{**cfg.__dict__, "root": self.docker.root(ws)})
        built = mcp_server.build_server(cfg)
        return {t.name: t for t in built._tool_manager.list_tools()}

    def list_tools(self, workspace_id: str, server: str, spec: Any) -> list[Listed]:
        if self.fail is not None:
            raise self.fail
        self.servers.add((workspace_id, server))
        return [
            Listed(t.name, t.description or "", t.parameters)
            for t in self._tools(workspace_id).values()
        ]

    def call(self, workspace_id, server, spec, tool, args, timeout_s):
        if self.fail is not None:
            raise self.fail
        self.servers.add((workspace_id, server))
        self.calls.append((tool, dict(args)))
        import anyio

        found = self._tools(workspace_id)[tool]
        kwargs = {
            ("from_" if k == "from" and tool == "workspace_move" else k): v for k, v in args.items()
        }
        if tool == "workspace_move":
            return anyio.run(lambda: found.fn(**{"from": kwargs.get("from_"), "to": kwargs["to"]}))
        return anyio.run(lambda: found.fn(**kwargs))

    def close_workspace(self, workspace_id: str) -> None:
        self.closed.append(workspace_id)

    def close_idle(self, idle_s: float = 600) -> int:
        return 0

    def third_party_count(self, workspace_id: str) -> int:
        return sum(1 for w, s in self.servers if w == workspace_id and s != "workspace")

    def has(self, workspace_id: str, server: str) -> bool:
        return (workspace_id, server) in self.servers


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, Any] = {}
        self.locked = False

    def get(self, key: str) -> Any:
        return self.data.get(key)

    def set(self, key: str, value: Any, ex: int | None = None) -> None:
        self.data[key] = value

    def lock(self, name: str, timeout: float, blocking_timeout: float) -> Any:
        parent = self
        return SimpleNamespace(acquire=lambda: not parent.locked, release=lambda: None)


class FakeCallbacks:
    def __init__(self) -> None:
        self.sent: list[tuple[str, Any]] = []

    def workspace_changed(self, message: Any) -> None:
        self.sent.append(("workspace_changed", message))

    def heartbeat(self, message: Any) -> None:
        self.sent.append(("heartbeat", message))

    def secrets_blocked(self, message: Any) -> None:
        self.sent.append(("secrets_blocked", message))

    def statuses(self) -> list[str]:
        return [m.status for k, m in self.sent if k == "workspace_changed"]


@pytest.fixture
def runner(tmp_path: Path) -> SimpleNamespace:
    settings = RunnerSettings(
        DH_IMAGE_PREFIX="ghcr.io/test", RUNNER_ID="runner-test", RUNNER_KEY="k"
    )
    docker = FakeDocker(settings, tmp_path / "containers")
    pool = FakePool(docker)
    callbacks = FakeCallbacks()
    redis = FakeRedis()
    service = RunnerService(settings, docker, pool, callbacks, redis)  # type: ignore[arg-type]
    return SimpleNamespace(
        service=service,
        docker=docker,
        pool=pool,
        callbacks=callbacks,
        redis=redis,
        settings=settings,
    )


STACK = {
    "language": "python",
    "framework": "none",
    "workspace_image": "dexterhouse/workspace:python",
    "package_manager": "uv",
    "test_command": "python3 -c 'print(\"2 passed\")'",
    "run_command": "python3 -m http.server 8000",
    "services": [],
    "env": {"APP_ENV": "test"},
}


@pytest.fixture
def stack() -> dict[str, Any]:
    return dict(STACK)


@pytest.fixture
def workspace(runner: SimpleNamespace) -> uuid.UUID:
    from dexterhouse_schema.runner import WorkspaceCreate

    ws = uuid.uuid4()
    result = runner.service.create(
        WorkspaceCreate(project_id=uuid.uuid4(), workspace_id=ws, stack=STACK)
    )
    assert result.ok, result
    return ws


__all__ = ["STACK", "RunnerError", "SessionError"]
