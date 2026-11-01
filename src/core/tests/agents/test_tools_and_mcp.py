# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tool catalog, MCP client and tool-gateway helpers."""

import sys
from types import SimpleNamespace

import pytest

from dexterhouse.apps.agents.services import events as events_module
from dexterhouse.apps.agents.services.mcp_client import (
    McpError,
    McpPool,
    interpolate,
    server_spec,
    spec_key,
    to_outcome,
)
from dexterhouse.apps.agents.services.packages import (
    PackageError,
    ToolBinding,
    builtin_tools_dir,
    load_agent_package,
    load_tool_catalog,
)
from dexterhouse.apps.agents.services.tool_gateway import check_args_policy, redact
from dexterhouse_schema.tool import Permission, Tool

from .conftest import FIXTURES, installed_root


def test_catalog_has_builtin_memory_and_installed_tools(tool_dirs):
    catalog = load_tool_catalog()
    memory = catalog.get("memory.search")
    assert memory is not None
    assert memory.builtin
    assert memory.root == installed_root("memory").resolve()
    assert (memory.root / "tool.yaml").read_bytes() == (
        builtin_tools_dir() / "memory" / "tool.yaml"
    ).read_bytes()
    echo = catalog.get("echo.say")
    assert echo is not None
    assert not echo.builtin
    assert catalog.get("git.push") is None
    assert load_tool_catalog([tool_dirs / "missing"]).bindings == {}


def test_agent_package_and_errors(tmp_path):
    package = load_agent_package(FIXTURES / "agents" / "test-analyst")
    assert package.name == "test-analyst"
    assert package.skills[0].tools_required == ("memory.search",)
    with pytest.raises(PackageError):
        load_agent_package(tmp_path)
    (tmp_path / "dexterhouse.yaml").write_text("schema: 1\nkind: agent\n", encoding="utf-8")
    with pytest.raises(PackageError, match="invalid"):
        load_agent_package(tmp_path)


def test_server_spec_for_builtin_and_installed_packages(tool_dirs, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://db/x")
    catalog = load_tool_catalog()
    variables = {
        "project.id": "p1",
        "project.organization_id": "o1",
        "project.data_residency": "local",
    }
    builtin = server_spec(catalog.get("memory.search"), variables)
    assert builtin.command == sys.executable
    assert builtin.args == ["-m", "dexterhouse.apps.agents.builtin_mcp"]
    assert builtin.cwd is None
    assert builtin.env["DH_PROJECT_ID"] == "p1"
    # the three built-in packages share one server process per turn
    assert spec_key(builtin) == spec_key(server_spec(catalog.get("project.ask"), variables))
    assert spec_key(builtin) == spec_key(server_spec(catalog.get("skills.read"), variables))
    assert builtin.env["DATABASE_URL"] == "postgres://db/x"
    installed = server_spec(catalog.get("echo.say"), variables)
    assert installed.env == {"ECHO_PROJECT": "p1"}  # no core secrets for third-party servers
    assert installed.cwd == installed_root("echo-tools").resolve()
    http = Tool.model_validate(
        {
            "schema": 1,
            "name": "web-tools",
            "transport": "http",
            "runs_in": "worker",
            "url": "https://mcp.example.com/mcp",
            "permissions": [{"id": "web.search", "mcp_tool": "search", "risk": "low"}],
            "network": "allowlist",
            "hosts": ["mcp.example.com"],
        }
    )
    binding = ToolBinding(http.permissions[0], http, tool_dirs, builtin=False)
    assert server_spec(binding, variables) == "https://mcp.example.com/mcp"
    assert interpolate("${project.id}-${project.unknown}", variables) == "p1-"


def test_pool_reports_servers_that_cannot_start(tool_dirs):
    tool = Tool.model_validate(
        {
            "schema": 1,
            "name": "broken-tools",
            "transport": "stdio",
            "runs_in": "worker",
            "command": ["bin/missing-server"],
            "permissions": [{"id": "broken.x", "mcp_tool": "x", "risk": "low"}],
            "network": "allowlist",
            "hosts": ["localhost"],
        }
    )
    binding = ToolBinding(tool.permissions[0], tool, tool_dirs, builtin=False)
    with McpPool({}, timeout_s=5) as pool:
        with pytest.raises(McpError, match="cannot start broken-tools"):
            pool.list_tools(binding)
    pool.close()  # idempotent


def test_pool_keeps_one_server_per_package(tool_dirs, echo_log):
    binding = load_tool_catalog().get("echo.say")
    with McpPool({"project.id": "p"}) as pool:
        names = {t.name for t in pool.list_tools(binding)}
        assert names == {"say", "write", "fail"}
        assert pool.call(binding, {"text": "a"}).content == "echo: a"
        assert pool.call(binding, {"text": "b"}).content == "echo: b"
    assert echo_log() == ["say p", "say p"]


def test_outcome_flattening():
    text = SimpleNamespace(
        content=[SimpleNamespace(text="hi")], structured_content={"result": "hi"}, is_error=False
    )
    assert to_outcome(text).content == "hi"
    structured = SimpleNamespace(content=[], structured_content={"a": 1}, is_error=True)
    outcome = to_outcome(structured)
    assert (outcome.content, outcome.is_error) == ('{"a": 1}', True)
    assert to_outcome(SimpleNamespace(content=[], structured_content=None)).content == ""


def test_args_policy_and_redaction():
    policy = {
        "repo": {"const": "/ws"},
        "mode": {"enum": ["a", "b"]},
        "path": {"pattern": r"^src/", "maxLength": 10},
        "n": {"minimum": 1, "maximum": 3},
    }
    ok = {"repo": "/ws", "mode": "a", "path": "src/x", "n": 2}
    assert check_args_policy(policy, ok) is None
    assert "must be '/ws'" in check_args_policy(policy, ok | {"repo": "/etc"})
    assert "one of" in check_args_policy(policy, ok | {"mode": "c"})
    assert "does not match" in check_args_policy(policy, ok | {"path": "etc/x"})
    assert "longer" in check_args_policy(policy, ok | {"path": "src/" + "x" * 20})
    assert "below" in check_args_policy(policy, ok | {"n": 0})
    assert "above" in check_args_policy(policy, ok | {"n": 9})
    assert redact({"api_key": "k", "nested": [{"password": "p", "x": 1}]}) == {
        "api_key": "***",
        "nested": [{"password": "***", "x": 1}],
    }


def test_speaker_throttles(monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(
        events_module, "emit_turn", lambda turn, kind, payload, **kw: sent.append(payload)
    )
    now = [0.0]
    turn = SimpleNamespace(id="t", agent_instance_id="a")
    speaker = events_module.Speaker(turn, clock=lambda: now[0])
    delta = SimpleNamespace(kind="text_delta", text="x" * 200)
    speaker(delta)  # first one goes out
    speaker(delta)  # within 0.5 s: buffered
    speaker(SimpleNamespace(kind="usage"))
    now[0] = 1.0
    speaker(delta)
    assert [p["seq"] for p in sent] == [1, 2]
    assert len(sent[1]["text"]) == events_module.SPEAKING_CHARS
    speaker.buffer = "  "
    speaker.flush()
    assert len(sent) == 2


def test_permission_model_accepts_descriptions():
    assert Permission(id="echo.say", mcp_tool="say", risk="low").description is None
