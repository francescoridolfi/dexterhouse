# SPDX-License-Identifier: AGPL-3.0-or-later
import sys
from types import SimpleNamespace

import pytest

from dexterhouse_runner.sessions import SessionError, SessionPool, decode


def test_spec_is_a_docker_exec():
    pool = SessionPool("docker")
    try:
        spec = pool.spec("dh-ws-1", ["dexterhouse-workspace-mcp"], {"A": "1"})
        assert spec.command == "docker"
        assert spec.args == [
            "exec",
            "-i",
            "-u",
            "1000:1000",
            "-w",
            "/workspace",
            "-e",
            "A=1",
            "dh-ws-1",
            "dexterhouse-workspace-mcp",
        ]
    finally:
        pool.close_workspace("dh-ws-1")


def test_decode():
    text = SimpleNamespace(text='{"ok": 1}')
    assert decode(SimpleNamespace(content=[text], structured_content=None)) == {"ok": 1}
    assert decode(SimpleNamespace(content=[], structured_content={"a": 1})) == {"a": 1}
    assert decode(
        SimpleNamespace(content=[SimpleNamespace(text="plain")], structured_content=None)
    ) == {"text": "plain"}
    failed = decode(
        SimpleNamespace(
            content=[SimpleNamespace(text="boom")], structured_content=None, is_error=True
        )
    )
    assert failed["error"]["code"] == "internal"
    assert decode(
        SimpleNamespace(content=[SimpleNamespace(text="[1]")], structured_content=None)
    ) == {"result": [1]}


def test_restart_budget():
    pool = SessionPool()
    assert not any(pool._died("w") for _ in range(3))
    assert pool._died("w")


@pytest.mark.slow
def test_real_session_with_the_local_server(tmp_path):
    """The workspace MCP server as a local process (no Docker): list, call, crash, restart."""
    from mcp import StdioServerParameters

    pool = SessionPool()
    spec = StdioServerParameters(
        command=sys.executable,
        args=["-m", "dexterhouse_runner.workspace_mcp"],
        env={"DH_WORKSPACE_ROOT": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )
    try:
        names = {t.name for t in pool.list_tools("w", "workspace", spec)}
        assert {"workspace_exec", "git_commit"} <= names
        wrote = pool.call(
            "w", "workspace", spec, "workspace_write", {"path": "a", "content": "b"}, 30
        )
        assert wrote["bytes"] == 1
        assert (
            pool.call("w", "workspace", spec, "workspace_exec", {"command": "cat a"}, 30)["stdout"]
            == "b"
        )
        with pytest.raises(SessionError):
            pool.call("w", "workspace", spec, "workspace_exec", {"command": "kill -9 $PPID"}, 30)
        errors = 0
        for _ in range(3):  # the dead session is dropped, the next call starts a new one
            try:
                listed = pool.call("w", "workspace", spec, "workspace_list", {}, 30)
                break
            except SessionError:
                errors += 1
        assert listed["entries"] == 1
        assert errors <= 2
    finally:
        pool.close_workspace("w")
