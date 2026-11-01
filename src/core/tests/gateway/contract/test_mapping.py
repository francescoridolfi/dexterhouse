# SPDX-License-Identifier: AGPL-3.0-or-later
"""Provider-specific request mapping: what each wire format receives from the neutral one."""

import hashlib
import json

import httpx2
import pytest

from dexterhouse.apps.gateway.messages import (
    ImagePart,
    Message,
    OpaquePart,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)
from dexterhouse.apps.gateway.providers import ProviderConfig, ProviderError, collect, get_provider
from dexterhouse.apps.gateway.providers.anthropic import FALLBACK_BETA, build_payload
from dexterhouse.apps.gateway.providers.anthropic_cli import TOOL_PREFIX, transcript
from dexterhouse.apps.gateway.providers.base import (
    classify_http_error,
    internal_tool_name,
    parse_args,
    wire_tool_name,
)
from dexterhouse.apps.gateway.tokens import bridge_key, verify_turn_token

from .conftest import Recorder, make_request, replay_client

THINKING = OpaquePart(
    provider="anthropic", data={"type": "thinking", "thinking": "", "signature": "sig"}
)
FOLLOW_UP = [
    Message(
        role="assistant",
        parts=[
            THINKING,
            TextPart(text="Searching."),
            ToolCallPart(id="call_1", name="memory.search", args={"query": "rules"}),
        ],
    ),
    Message(
        role="tool", parts=[ToolResultPart(call_id="call_1", content="no hits", is_error=True)]
    ),
]


def test_tool_names_are_reversible():
    assert wire_tool_name("workspace.exec_tests") == "workspace__exec_tests"
    assert internal_tool_name("workspace__exec_tests") == "workspace.exec_tests"
    assert parse_args("[1]") == {"_value": [1]}
    assert parse_args("{bad") == {"_raw": "{bad"}


def test_http_error_classification():
    assert classify_http_error(408, "slow").status == "timeout"
    assert classify_http_error(429, "x", {"retry-after": "120"}).retry_after == 60.0
    assert classify_http_error(429, "x", {"retry-after": "soon"}).retry_after is None
    assert classify_http_error(404, "no model").code == "configuration"
    assert classify_http_error(422, "odd").retryable is False


# anthropic -------------------------------------------------------------------------------


def test_anthropic_payload_caching_tools_and_results():
    payload = build_payload(make_request("claude-sonnet-5-5", FOLLOW_UP), {"effort": "high"})
    assert "temperature" not in payload  # rejected by current models
    assert payload["output_config"] == {"effort": "high"}
    assert payload["fallbacks"] == "default"
    assert payload["betas"] == [FALLBACK_BETA]
    assert payload["system"] == [
        {"type": "text", "text": "You are the Analyst.", "cache_control": {"type": "ephemeral"}}
    ]
    assert [m["role"] for m in payload["messages"]] == ["user", "assistant", "user"]
    assistant = payload["messages"][1]["content"]
    assert assistant[0] == {"type": "thinking", "thinking": "", "signature": "sig"}
    assert assistant[2] == {
        "type": "tool_use",
        "id": "call_1",
        "name": "memory__search",
        "input": {"query": "rules"},
    }
    result = payload["messages"][2]["content"][0]
    assert result["type"] == "tool_result"
    assert result["is_error"] is True
    assert result["cache_control"] == {"type": "ephemeral"}  # conversation tail breakpoint
    assert payload["tools"][0]["name"] == "memory__search"


def test_anthropic_payload_limits_breakpoints_and_drops_foreign_parts():
    flagged = [
        Message(role="user", parts=[TextPart(text=f"m{i}")], cache_breakpoint=True)
        for i in range(6)
    ]
    foreign = Message(
        role="assistant",
        parts=[OpaquePart(provider="other", data={"x": 1}), TextPart(text=""), TextPart(text="ok")],
    )
    request = make_request("claude-haiku-5-5", [*flagged, foreign])
    payload = build_payload(request, {"refusal_fallback": False})
    blocks = list(payload["system"]) + [b for m in payload["messages"] for b in m["content"]]
    assert sum("cache_control" in b for b in blocks) == 4
    assert blocks[-1]["cache_control"] == {"type": "ephemeral"}
    assert payload["messages"][-1]["content"] == [
        {"type": "text", "text": "ok", "cache_control": {"type": "ephemeral"}}
    ]
    assert "fallbacks" not in payload
    image = make_request("claude-haiku-5-5")
    image.messages[1].parts.append(ImagePart(media_type="image/png", data="AAAA"))
    assert build_payload(image)["messages"][0]["content"][1]["source"]["type"] == "base64"


def test_anthropic_thinking_blocks_are_kept_opaque():
    events = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "m",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-opus-5-5",
                    "content": [],
                    "stop_reason": None,
                    "usage": {"input_tokens": 10, "output_tokens": 1},
                },
            },
        ),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "thinking", "thinking": "", "signature": ""},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "plan"},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "signature_delta", "signature": "EqQB"},
            },
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 1,
                "content_block": {"type": "text", "text": "Done"},
            },
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 1}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "refusal"},
                "usage": {"output_tokens": 3},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    body = []
    for name, data in events:
        body += [f"event: {name}", f"data: {json.dumps(data)}", ""]
    cassette = {"status": 200, "headers": {"content-type": "text/event-stream"}, "body": body}
    recorder = Recorder()
    provider = get_provider(
        "anthropic", ProviderConfig(api_key="k", http_client=replay_client(cassette, recorder))
    )
    result = collect(
        provider.stream(make_request("claude-opus-5-5")), provider="anthropic", model="m"
    )
    assert result.message.parts[0] == OpaquePart(
        provider="anthropic", data={"type": "thinking", "thinking": "plan", "signature": "EqQB"}
    )
    assert result.message.text() == "Done"
    assert result.stop_reason == "refusal"
    assert recorder.bodies[0]["fallbacks"] == "default"


# openai / openai-compatible ---------------------------------------------------------------


def test_openai_payload(build):
    provider, _, _ = build("openai", "text")
    request = make_request("gpt-5", FOLLOW_UP)
    request.messages[1].parts.append(ImagePart(media_type="image/png", data="AAAA"))
    payload = provider.build_payload(request)
    assert "temperature" not in payload  # reasoning models accept only the default
    assert payload["max_completion_tokens"] == 512
    assert payload["stream_options"] == {"include_usage": True}
    messages = payload["messages"]
    assert messages[0] == {"role": "system", "content": "You are the Analyst."}
    assert messages[1]["content"][1]["image_url"]["url"] == "data:image/png;base64,AAAA"
    assert messages[2]["tool_calls"][0]["function"] == {
        "name": "memory__search",
        "arguments": '{"query": "rules"}',
    }
    assert messages[3] == {"role": "tool", "tool_call_id": "call_1", "content": "ERROR: no hits"}
    assert payload["tools"][0]["function"]["name"] == "memory__search"


def test_openai_compatible_payload_and_configuration(build, monkeypatch):
    provider, recorder, cassette = build("openai-compatible", "text", is_local=True, tools=False)
    payload = provider.build_payload(make_request("llama", FOLLOW_UP))
    assert payload["max_tokens"] == 512
    assert payload["temperature"] == 0.2
    assert provider.capabilities().local is True
    assert provider.capabilities().tools is False
    list(provider.stream(make_request(cassette["model"])))
    assert recorder.urls[0] == "http://provider.test/v1/chat/completions"
    monkeypatch.delenv("OPENAI_COMPATIBLE_BASE_URL", raising=False)
    with pytest.raises(ProviderError) as info:
        get_provider("openai-compatible")
    assert info.value.code == "configuration"


# ollama -----------------------------------------------------------------------------------


def test_ollama_payload_and_unreachable(build):
    provider, recorder, cassette = build("ollama", "text")
    payload = provider.build_payload(make_request(cassette["model"], FOLLOW_UP))
    assert payload["options"] == {"temperature": 0.2, "num_predict": 512}
    assert payload["messages"][2]["tool_calls"] == [
        {"function": {"name": "memory__search", "arguments": {"query": "rules"}}}
    ]
    assert payload["messages"][3] == {"role": "tool", "content": "ERROR: no hits"}
    assert provider.capabilities().local is True
    list(provider.stream(make_request(cassette["model"])))
    assert recorder.urls[0].endswith("/api/chat")

    def refuse(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connection refused")

    down = get_provider(
        "ollama", ProviderConfig(http_client=httpx2.Client(transport=httpx2.MockTransport(refuse)))
    )
    with pytest.raises(ProviderError) as info:
        list(down.stream(make_request(cassette["model"])))
    assert info.value.retryable


def test_ollama_error_line_mid_stream(build):
    cassette = {"status": 200, "headers": {}, "body": ['{"error": "model crashed"}']}
    provider = get_provider(
        "ollama", ProviderConfig(http_client=replay_client(cassette, Recorder()))
    )
    with pytest.raises(ProviderError, match="model crashed"):
        list(provider.stream(make_request("qwen3:14b")))


# anthropic-cli ----------------------------------------------------------------------------


def test_cli_command_bridge_and_transcript(build, settings):
    provider, recorder, cassette = build("anthropic-cli", "tool_use")
    list(provider.stream(make_request(cassette["model"], FOLLOW_UP)))
    record = recorder.cli
    argv = record["argv"]
    for flag, value in [
        ("--output-format", "stream-json"),
        ("--input-format", "stream-json"),
        ("--max-turns", "1"),
        ("--model", cassette["model"]),
        ("--permission-mode", "dontAsk"),
        ("--allowedTools", f"{TOOL_PREFIX}*"),
    ]:
        assert argv[argv.index(flag) + 1] == value
    assert "--strict-mcp-config" in argv
    assert "Bash" in argv[argv.index("--disallowedTools") + 1]
    assert record["system"] == "You are the Analyst."
    assert record["cwd"].endswith("cwd")

    server = record["mcp"]["mcpServers"]["dexterhouse"]
    assert server["args"] == ["-m", "dexterhouse.apps.gateway.bridge"]
    env = server["env"]
    assert env["DH_BRIDGE_KEY"] == bridge_key(settings.SECRET_KEY)
    claims = verify_turn_token(
        env["DH_TURN_TOKEN"],
        key=env["DH_BRIDGE_KEY"],
        tools_sha256=hashlib.sha256(record["tools_raw"].encode()).hexdigest(),
    )
    assert claims["sub"] == "0195f3b0-0000-7000-8000-000000000001"
    assert json.loads(record["tools_raw"])[0]["name"] == "memory__search"

    message = json.loads(record["stdin"])
    assert message["type"] == "user"
    text = message["message"]["content"]
    assert f"[tool call call_1] {TOOL_PREFIX}memory__search" in text
    assert "[tool result call_1 error]" in text


def test_cli_without_tools_has_no_mcp_config(build):
    provider, recorder, cassette = build("anthropic-cli", "text")
    request = make_request(cassette["model"])
    request.tools.clear()
    list(provider.stream(request))
    argv = recorder.cli["argv"]
    assert "--mcp-config" not in argv
    assert "--strict-mcp-config" in argv  # no user MCP servers either
    assert json.loads(recorder.cli["stdin"])["message"]["content"] == "Summarise the brief."


def test_cli_hides_api_key_and_uses_dedicated_home(build, monkeypatch, tmp_path):
    from dexterhouse.apps.gateway.conf import get_gateway_env

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-not-leak")  # pragma: allowlist secret
    monkeypatch.setenv("CLAUDE_CLI_HOME", str(tmp_path))
    get_gateway_env.cache_clear()
    provider, recorder, cassette = build("anthropic-cli", "text")
    list(provider.stream(make_request(cassette["model"])))
    assert recorder.cli["home"] == str(tmp_path)
    assert provider._process_env().get("ANTHROPIC_API_KEY") is None


@pytest.mark.parametrize(
    ("version", "message"),
    [("1.0.0 (Claude Code)", "< 2.0.0"), ("garbage", "unrecognised")],
)
def test_cli_version_gate(build, monkeypatch, version, message):
    monkeypatch.setenv("FAKE_CLAUDE_VERSION", version)
    provider, _, cassette = build("anthropic-cli", "text")
    with pytest.raises(ProviderError, match=message) as info:
        list(provider.stream(make_request(cassette["model"])))
    assert info.value.code == "configuration"


def test_cli_missing_binary(monkeypatch):
    from dexterhouse.apps.gateway.conf import get_gateway_env

    monkeypatch.setenv("CLAUDE_CLI_PATH", "/nonexistent/claude")
    get_gateway_env.cache_clear()
    with pytest.raises(ProviderError, match="not found") as info:
        list(get_provider("anthropic-cli").stream(make_request("claude-sonnet-5-5")))
    assert info.value.code == "configuration"
    get_gateway_env.cache_clear()


def test_cli_timeout_kills_the_process(build, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_SLEEP", "5")
    provider, _, cassette = build("anthropic-cli", "text", timeout_s=1)
    with pytest.raises(ProviderError) as info:
        list(provider.stream(make_request(cassette["model"])))
    assert info.value.status == "timeout"


def test_cli_transcript_single_user_message():
    assert transcript(make_request("m")) == "Summarise the brief."
