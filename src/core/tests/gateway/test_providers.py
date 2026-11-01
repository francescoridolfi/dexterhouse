# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

import pytest

from dexterhouse.apps.gateway.messages import (
    TextDelta,
    TextPart,
    ToolCallDelta,
    ToolCallEnd,
    ToolCallPart,
    ToolCallStart,
    ToolResultPart,
)
from dexterhouse.apps.gateway.providers import (
    FakeProvider,
    Provider,
    ProviderError,
    UnknownProviderError,
    collect,
    get_provider,
)
from dexterhouse.apps.gateway.providers.base import parse_args
from dexterhouse.apps.gateway.providers.fake import FakeResponse, estimate_tokens

CASSETTES = Path(__file__).parent / "cassettes"


def test_registry_returns_fake():
    provider = get_provider("fake")
    assert isinstance(provider, Provider)
    with pytest.raises(UnknownProviderError):
        get_provider("skynet")


def test_echo_streams_text_usage_and_stop(make_request):
    provider = FakeProvider()
    events = list(provider.stream(make_request("a" * 40)))
    assert [type(e).__name__ for e in events[:3]] == ["TextDelta", "TextDelta", "TextDelta"]
    result = collect(events, provider="fake", model="fake-model")
    assert result.message.text() == "fake: " + "a" * 40
    assert result.stop_reason == "end"
    assert result.usage.input == estimate_tokens("You are an agent.") + estimate_tokens("a" * 40)
    assert provider.requests[0].model == "fake-model"


def test_cassette_tool_call_then_answer(make_request):
    provider = FakeProvider.from_cassette(CASSETTES / "tool_then_answer.json")
    first = collect(provider.stream(make_request()), provider="fake", model="m")
    assert first.stop_reason == "tool_use"
    assert first.message.parts[0] == TextPart(text="Let me read the brief.")
    assert first.message.parts[1] == ToolCallPart(
        id="call_1", name="workspace.read", args={"path": "brief.md"}
    )
    assert first.usage.cached_read == 1000
    second = collect(provider.stream(make_request()), provider="fake", model="m")
    assert second.message.text().startswith('{"status"')
    third = collect(provider.stream(make_request("again")), provider="fake", model="m")
    assert third.message.text() == "fake: again"


@pytest.mark.parametrize("status", ["error", "rate_limited", "timeout"])
def test_scripted_errors(make_request, status):
    provider = FakeProvider([FakeResponse(error=status)])
    with pytest.raises(ProviderError) as info:
        list(provider.stream(make_request()))
    assert info.value.status == status


def test_collect_handles_chunked_and_invalid_tool_args():
    events = [
        ToolCallStart(id="a", name="x"),
        ToolCallDelta(id="a", args_json_chunk='{"k": '),
        ToolCallDelta(id="a", args_json_chunk="1}"),
        ToolCallEnd(id="a"),
        TextDelta(text="after"),
    ]
    result = collect(events, provider="p", model="m")
    assert result.message.parts[0] == ToolCallPart(id="a", name="x", args={"k": 1})
    assert result.message.text() == "after"


@pytest.mark.parametrize(
    ("raw", "expected"), [("", {}), ("{bad", {"_raw": "{bad"}), ("[1]", {"_value": [1]})]
)
def test_parse_args(raw, expected):
    assert parse_args(raw) == expected


def test_message_parts_are_discriminated():
    from dexterhouse.apps.gateway.messages import Message

    message = Message.model_validate(
        {"role": "tool", "parts": [{"kind": "tool_result", "call_id": "a", "content": "ok"}]}
    )
    assert message.parts == [ToolResultPart(call_id="a", content="ok")]
    assert message.text() == ""
