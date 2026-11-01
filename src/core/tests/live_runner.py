# SPDX-License-Identifier: AGPL-3.0-or-later
"""The real runner for `slow` and `security` tests: Docker, the workspace image, Squid.

`RunnerService` runs in the test process against the local Docker daemon (the same code the
`runner` worker runs; the Celery transport has its own test), with the egress proxy of
`docker/proxy` in a container `dh-test-proxy`. Workspaces are named `dh-test-ws-<id>` and
everything is removed at the end of the session. `InProcessRunnerClient` lets the core call
it as it would call the worker: fire-and-forget messages run after the commit and the
callbacks go straight to `workspaces.services`.

Needs the workspace image (`DH_TEST_WORKSPACE_IMAGE`, default
`ghcr.io/francescoridolfi/dexterhouse-workspace:python`), built with
`docker build -f docker/Dockerfile.workspace-python -t <image> .`.
"""

import os
import time
import uuid
from pathlib import Path
from typing import Any

import docker
import pytest
import redis
from django.conf import settings
from django.db import transaction
from docker.errors import ImageNotFound, NotFound

from dexterhouse_runner.config import RunnerSettings
from dexterhouse_runner.docker_manager import DockerManager
from dexterhouse_runner.service import TASK_METHODS, RunnerService
from dexterhouse_runner.sessions import SessionPool
from dexterhouse_schema.runner import (
    Limits,
    ToolInvoke,
    ToolResult,
    WorkspaceCreate,
    WorkspaceDestroy,
)

IMAGE = os.environ.get(
    "DH_TEST_WORKSPACE_IMAGE", "ghcr.io/francescoridolfi/dexterhouse-workspace:python"
)
SQUID = (
    "ubuntu/squid:6.10-24.10_beta"
    "@sha256:c9f5212b147a766529c7b026e2bebed37b998d33d0066b658596af5eba7cc65c"
)
PREFIX = "dh-test-ws"
PROXY = "dh-test-proxy"
EGRESS = "dh-test-egress"
REPO = Path(__file__).resolve().parents[3]
STACK = {
    "language": "python",
    "framework": "stdlib",
    "workspace_image": "dexterhouse/workspace:python",
    "package_manager": "pip",
    "test_command": "python3 -m unittest discover -s tests -t . -v",
    "run_command": "python3 -m http.server 8000",
    "services": [],
    "ports": [8000],
}


class RecordingCallbacks:
    """Keeps every callback; with `forward` also applies them in the core (in-process)."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, Any]] = []
        self.forward = False

    def workspace_changed(self, message: Any) -> None:
        self.sent.append(("workspace_changed", message))
        if self.forward:
            from dexterhouse.apps.workspaces import services

            services.apply_changed(message)

    def heartbeat(self, message: Any) -> None:
        self.sent.append(("heartbeat", message))

    def secrets_blocked(self, message: Any) -> None:
        self.sent.append(("secrets_blocked", message))
        if self.forward:
            from dexterhouse.apps.workspaces import events

            events.secrets_blocked(message)


class InProcessRunnerClient:
    """`RunnerClient` over a `RunnerService` in this process."""

    inline = False

    def __init__(self, service: RunnerService) -> None:
        self.service = service
        self.calls: list[tuple[str, Any]] = []

    def call(self, task: str, message: Any, timeout_s: float | None = None) -> ToolResult:
        self.calls.append((task, message))
        return getattr(self.service, TASK_METHODS[task])(message)

    def send(self, task: str, message: Any) -> None:
        transaction.on_commit(lambda: self.call(task, message), robust=False)


def _wait_port(container: Any, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        code, _ = container.exec_run(["bash", "-c", "exec 3<>/dev/tcp/127.0.0.1/3128"])
        if code == 0:
            return
        time.sleep(0.5)
    raise RuntimeError("the test proxy did not start")


@pytest.fixture(scope="session")
def docker_client() -> Any:
    client = docker.from_env(timeout=120)
    client.ping()
    try:
        client.images.get(IMAGE)
    except ImageNotFound:
        build = f"docker build -f docker/Dockerfile.workspace-python -t {IMAGE} ."
        pytest.fail(f"workspace image {IMAGE} missing: {build}")
    return client


@pytest.fixture(scope="session")
def egress_proxy(docker_client: Any) -> Any:
    for stale in docker_client.containers.list(all=True, filters={"name": PROXY}):
        stale.remove(force=True)
    networks = docker_client.networks.list(names=[EGRESS])
    network = networks[0] if networks else docker_client.networks.create(EGRESS, driver="bridge")
    proxy = docker_client.containers.run(
        SQUID,
        name=PROXY,
        detach=True,
        entrypoint=["/bin/bash", "/etc/dh-proxy/entrypoint.sh"],
        environment={"WORKSPACE_EGRESS_ALLOWLIST": "pypi.org,files.pythonhosted.org"},
        volumes={str(REPO / "docker" / "proxy"): {"bind": "/etc/dh-proxy", "mode": "ro"}},
        network=network.name,
        labels={"dexterhouse.test": "e05"},
    )
    _wait_port(proxy)
    yield proxy
    proxy.remove(force=True)
    try:
        network.remove()
    except NotFound:
        pass


@pytest.fixture(scope="session")
def runner_settings() -> RunnerSettings:
    return RunnerSettings(
        REDIS_URL=settings.REDIS_URL,
        RUNNER_ID="dh-test-runner",
        RUNNER_KEY=settings.RUNNER_KEY,
        WORKSPACE_PREFIX=PREFIX,
        PROXY_CONTAINER=PROXY,
        WORKSPACE_PULL=False,
        DH_IMAGE_PREFIX=IMAGE.rsplit("/dexterhouse-workspace", 1)[0],
        RUNNER_METRICS_PORT=0,
    )


@pytest.fixture(scope="session")
def live_runner(
    docker_client: Any, egress_proxy: Any, runner_settings: RunnerSettings
) -> RunnerService:
    service = RunnerService(
        runner_settings,
        DockerManager(runner_settings, docker_client),
        SessionPool(),
        RecordingCallbacks(),  # type: ignore[arg-type]
        redis.Redis.from_url(settings.REDIS_URL),
    )
    yield service
    for workspace_id in list(service.docker.managed()):
        service.destroy(WorkspaceDestroy(workspace_id=workspace_id))


def create_workspace(
    service: RunnerService, stack: dict[str, Any] | None = None, **limits: Any
) -> uuid.UUID:
    workspace_id = uuid.uuid4()
    result = service.create(
        WorkspaceCreate(
            project_id=uuid.uuid4(),
            workspace_id=workspace_id,
            stack=stack or STACK,
            limits=Limits(**limits),
        )
    )
    assert result.ok, result.error
    return workspace_id


def destroy_workspace(service: RunnerService, workspace_id: uuid.UUID) -> None:
    service.destroy(WorkspaceDestroy(workspace_id=workspace_id))


def run(
    service: RunnerService, workspace_id: uuid.UUID, command: str, timeout_s: int = 30
) -> ToolResult:
    """`workspace.exec` as an agent would call it."""
    return tool(service, workspace_id, "workspace_exec", command=command, timeout_s=timeout_s)


def tool(service: RunnerService, workspace_id: uuid.UUID, name: str, **args: Any) -> ToolResult:
    return service.invoke(
        ToolInvoke(
            workspace_id=workspace_id,
            turn_id=uuid.uuid4(),
            seq=1,
            tool=name,
            args=args,
            timeout_s=int(args.get("timeout_s", 120)),
            agent_display_name="Tester",
        )
    )


def output(result: ToolResult) -> str:
    data = result.data or {}
    return f"{data.get('stdout', '')}\n{data.get('stderr', '')}"
