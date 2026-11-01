# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Celery transport end to end: the `runner` worker process, Redis, the core's client."""

import json
import os
import subprocess
import sys
import time
import uuid

import pytest
import redis
from celery import Celery
from django.conf import settings

from dexterhouse.apps.workspaces import client as client_module
from dexterhouse.apps.workspaces.client import CeleryRunnerClient
from dexterhouse_schema.runner import (
    ToolInvoke,
    ToolList,
    WorkspaceCreate,
    WorkspaceDestroy,
    WorkspaceStatusQuery,
)
from tests.live_runner import IMAGE, PREFIX, PROXY, STACK

pytestmark = pytest.mark.slow  # a Celery worker process and a workspace container


@pytest.fixture
def broker() -> str:
    url = settings.REDIS_URL.rsplit("/", 1)[0] + "/9"  # a database of its own
    redis.Redis.from_url(url).flushdb()
    yield url
    redis.Redis.from_url(url).flushdb()


@pytest.fixture
def worker(broker, egress_proxy):
    env = {
        **os.environ,
        "REDIS_URL": broker,
        "RUNNER_ID": "dh-test-celery",
        "RUNNER_KEY": "unused",
        "WORKSPACE_PREFIX": PREFIX,
        "PROXY_CONTAINER": PROXY,
        "WORKSPACE_PULL": "false",
        "DH_IMAGE_PREFIX": IMAGE.rsplit("/dexterhouse-workspace", 1)[0],
        "RUNNER_METRICS_PORT": "0",
        "RUNNER_HEARTBEAT_S": "1",
        "RUNNER_CONCURRENCY": "2",
    }
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "dexterhouse_runner.cli",
            "worker",
            "--without-gossip",
            "--without-mingle",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    yield process
    process.terminate()
    try:
        process.wait(20)
    except subprocess.TimeoutExpired:
        process.kill()


def test_round_trip_through_the_runner_queue(broker, worker, monkeypatch):
    app = Celery("core-test", broker=broker, backend=broker, set_as_current=False)
    monkeypatch.setattr(client_module, "celery_app", app)
    monkeypatch.setattr(client_module, "runner_heartbeats", lambda: {"dh-test-celery": {}})
    client = CeleryRunnerClient()
    probe = WorkspaceStatusQuery(workspace_id=uuid.uuid4())
    deadline = time.monotonic() + 60
    status = client.call("runner.workspace.status", probe, timeout_s=5)
    while (
        status.error is not None
        and status.error.code in ("timeout", "internal")
        and time.monotonic() < deadline
    ):
        status = client.call("runner.workspace.status", probe, timeout_s=5)
    assert status.data["status"] == "destroyed"

    workspace = uuid.uuid4()
    created = client.call(
        "runner.workspace.create",
        WorkspaceCreate(project_id=uuid.uuid4(), workspace_id=workspace, stack=STACK),
        timeout_s=120,
    )
    try:
        assert created.ok, created.error
        listed = client.call("runner.tool.list", ToolList(workspace_id=workspace))
        assert "workspace_exec" in {t["name"] for t in listed.data["tools"]}
        echoed = client.call(
            "runner.tool.invoke",
            ToolInvoke(
                workspace_id=workspace,
                turn_id=uuid.uuid4(),
                seq=1,
                tool="workspace_exec",
                args={"command": "echo hello from $(id -u)"},
            ),
            timeout_s=60,
        )
        assert echoed.data["stdout"].strip() == "hello from 1000"
        assert echoed.duration_ms > 0
    finally:
        client.call("runner.workspace.destroy", WorkspaceDestroy(workspace_id=workspace))
    queue = redis.Redis.from_url(broker)
    names = set()
    for raw in queue.lrange("core-callbacks", 0, -1):
        names.add(json.loads(raw)["headers"]["task"])
    assert {"core.runner.workspace_changed", "core.runner.heartbeat"} <= names
