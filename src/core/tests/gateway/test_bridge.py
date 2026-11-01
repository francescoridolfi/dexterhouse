# SPDX-License-Identifier: AGPL-3.0-or-later
"""The MCP bridge the Claude Code CLI talks to: signed tool list, intercepted calls."""

import hashlib
import json

import jwt
import pytest
from mcp import Client

from dexterhouse.apps.gateway import bridge
from dexterhouse.apps.gateway.tokens import bridge_key, issue_turn_token, verify_turn_token

SPECS = [{"name": "memory__search", "description": "Search", "input_schema": {"type": "object"}}]


@pytest.fixture
def bridge_env(tmp_path):
    tools = tmp_path / "tools.json"
    tools.write_text(json.dumps(SPECS), encoding="utf-8")
    key = bridge_key("secret")
    token = issue_turn_token(
        key=key, turn_id="t1", tools_sha256=hashlib.sha256(tools.read_bytes()).hexdigest()
    )
    return {"DH_BRIDGE_TOOLS": str(tools), "DH_BRIDGE_KEY": key, "DH_TURN_TOKEN": token}


def test_load_specs_checks_the_signed_tool_list(bridge_env, tmp_path):
    assert bridge.load_specs(bridge_env) == SPECS
    with pytest.raises(jwt.InvalidTokenError):
        bridge.load_specs({**bridge_env, "DH_BRIDGE_KEY": bridge_key("other")})
    tampered = tmp_path / "tools.json"
    tampered.write_text(json.dumps([*SPECS, {"name": "x", "input_schema": {}}]), encoding="utf-8")
    with pytest.raises(jwt.InvalidTokenError, match="tool list"):
        bridge.load_specs(bridge_env)


def test_expired_token_is_rejected():
    key = bridge_key("secret")
    token = issue_turn_token(key=key, turn_id=None, tools_sha256="s", ttl_s=-1)
    with pytest.raises(jwt.ExpiredSignatureError):
        verify_turn_token(token, key=key)


def test_main_refuses_without_token(monkeypatch, capsys):
    monkeypatch.delenv("DH_BRIDGE_TOOLS", raising=False)
    assert bridge.main() == 1
    assert "refusing to start" in capsys.readouterr().err


async def test_server_lists_tools_and_defers_calls():
    async with Client(bridge.build_server(SPECS)) as client:
        listed = await client.list_tools()
        assert [t.name for t in listed.tools] == ["memory__search"]
        result = await client.call_tool("memory__search", {"query": "x"})
        assert not result.is_error
        assert result.content[0].text == bridge.DEFERRED
        denied = await client.call_tool("workspace__exec", {})
        assert denied.is_error
