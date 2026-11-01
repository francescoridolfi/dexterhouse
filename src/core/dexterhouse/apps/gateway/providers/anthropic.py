# SPDX-License-Identifier: AGPL-3.0-or-later
"""`anthropic`: Messages API through the official SDK, with prompt caching (D-16).

The stable prefix (sections 1-5 of the context builder) ends at the message flagged
`cache_breakpoint`: its last block gets `cache_control`, and a second breakpoint goes on the
tail of the conversation so later calls of the same turn hit the cache (max 4 breakpoints).

Current models think adaptively and reject sampling parameters, so `temperature` is not
sent; depth is the profile option `effort` (`output_config.effort`). Thinking and fallback
blocks come back as `OpaquePart` and are echoed unchanged on the next call of the turn, as
the API requires within a tool-use loop. On models with server-side refusal fallbacks the
request opts in (`fallbacks: "default"`) unless the profile sets `refusal_fallback: false`.
"""

from collections.abc import Iterator, Mapping
from typing import Any

import anthropic

from dexterhouse.apps.gateway.conf import get_gateway_env
from dexterhouse.apps.gateway.messages import (
    CompletionRequest,
    ImagePart,
    OpaqueBlock,
    OpaquePart,
    Stop,
    StopReason,
    StreamEvent,
    TextDelta,
    TextPart,
    ToolCallDelta,
    ToolCallEnd,
    ToolCallPart,
    ToolCallStart,
    ToolResultPart,
    Usage,
)
from dexterhouse.apps.gateway.providers.base import (
    Capabilities,
    ProviderConfig,
    ProviderError,
    classify_http_error,
    internal_tool_name,
    wire_tool_name,
)

MAX_BREAKPOINTS = 4
EPHEMERAL = {"type": "ephemeral"}
OPAQUE_TYPES = frozenset({"thinking", "redacted_thinking", "fallback"})
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = frozenset(
    {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}
)
_STOP: dict[str, StopReason] = {
    "end_turn": "end",
    "stop_sequence": "end",
    "pause_turn": "end",
    "tool_use": "tool_use",
    "max_tokens": "max_tokens",
    "model_context_window_exceeded": "max_tokens",
    "refusal": "refusal",
}


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, config: ProviderConfig | None = None) -> None:
        config = config or ProviderConfig()
        self.options = config.options
        env = get_gateway_env()
        self.client = anthropic.Anthropic(
            api_key=config.api_key or env.ANTHROPIC_API_KEY or None,
            base_url=config.base_url or env.ANTHROPIC_BASE_URL or None,
            max_retries=0,  # the gateway retries with its own policy and breaker
            timeout=config.timeout_s or env.GATEWAY_TIMEOUT_S,
            http_client=config.http_client,
        )

    def capabilities(self) -> Capabilities:
        return Capabilities(tools=True, vision=True, max_context=200_000)

    def stream(self, request: CompletionRequest) -> Iterator[StreamEvent]:
        try:
            payload = build_payload(request, self.options)
            if "fallbacks" in payload:
                events = self.client.beta.messages.create(**payload, stream=True)
            else:
                events = self.client.messages.create(**payload, stream=True)
            yield from _translate(events)
        except anthropic.APIStatusError as exc:
            raise classify_http_error(
                exc.status_code, _error_message(exc), exc.response.headers
            ) from exc
        except anthropic.APITimeoutError as exc:
            raise ProviderError(str(exc), status="timeout", retryable=True) from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError(str(exc), retryable=True) from exc


def build_payload(
    request: CompletionRequest, options: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """The Messages API body for `request` (public for the contract tests)."""
    options = options or {}
    system: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = []
    for message in request.messages:
        blocks = [_block(part) for part in message.parts if _sendable(part)]
        if not blocks:
            continue
        if message.cache_breakpoint:
            blocks[-1]["cache_control"] = dict(EPHEMERAL)
        if message.role == "system":
            system.extend(blocks)
            continue
        role = "assistant" if message.role == "assistant" else "user"
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"].extend(blocks)
        else:
            messages.append({"role": role, "content": blocks})
    _cache_tail(system, messages)
    payload: dict[str, Any] = {
        "model": request.model,
        "max_tokens": request.max_tokens,
        "messages": messages,
    }
    if options.get("effort"):
        payload["output_config"] = {"effort": options["effort"]}
    if options.get("refusal_fallback", True) and request.model in FALLBACK_MODELS:
        payload["betas"] = [FALLBACK_BETA]
        payload["fallbacks"] = "default"
    if system:
        payload["system"] = system
    if request.tools:
        payload["tools"] = [
            {
                "name": wire_tool_name(t.name),
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in request.tools
        ]
    return payload


def _sendable(part: Any) -> bool:
    if isinstance(part, TextPart):
        return bool(part.text)
    return not isinstance(part, OpaquePart) or part.provider == AnthropicProvider.name


def _block(part: Any) -> dict[str, Any]:
    if isinstance(part, OpaquePart):
        return dict(part.data)
    if isinstance(part, TextPart):
        return {"type": "text", "text": part.text}
    if isinstance(part, ImagePart):
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": part.media_type, "data": part.data},
        }
    if isinstance(part, ToolCallPart):
        return {
            "type": "tool_use",
            "id": part.id,
            "name": wire_tool_name(part.name),
            "input": part.args,
        }
    if not isinstance(part, ToolResultPart):
        raise TypeError(f"unsupported part {type(part).__name__}")
    return {
        "type": "tool_result",
        "tool_use_id": part.call_id,
        "content": part.content,
        "is_error": part.is_error,
    }


def _cache_tail(system: list[dict[str, Any]], messages: list[dict[str, Any]]) -> None:
    """Add the conversation-tail breakpoint, keeping the total within the API limit."""
    flagged = [b for b in system if "cache_control" in b]
    flagged += [b for m in messages for b in m["content"] if "cache_control" in b]
    if not messages or not flagged:
        return  # no stable prefix declared: caching is opt-in through the context builder
    tail = messages[-1]["content"][-1]
    if "cache_control" not in tail:
        flagged.append(tail)
        tail["cache_control"] = dict(EPHEMERAL)
    for block in flagged[MAX_BREAKPOINTS - 1 : -1]:
        del block["cache_control"]


def _translate(events: Any) -> Iterator[StreamEvent]:
    tool_ids: dict[int, str] = {}
    opaque: dict[int, dict[str, Any]] = {}
    usage = Usage()
    reason: StopReason = "end"
    for event in events:
        kind = event.type
        if kind == "message_start":
            usage = _usage(event.message.usage, usage)
        elif kind == "content_block_start":
            block = event.content_block
            if block.type == "tool_use":
                tool_ids[event.index] = block.id
                yield ToolCallStart(id=block.id, name=internal_tool_name(block.name))
            elif block.type == "text" and block.text:
                yield TextDelta(text=block.text)
            elif block.type in OPAQUE_TYPES:
                opaque[event.index] = block.to_dict()
        elif kind == "content_block_delta":
            delta = event.delta
            if delta.type == "text_delta":
                yield TextDelta(text=delta.text)
            elif delta.type == "input_json_delta" and event.index in tool_ids:
                yield ToolCallDelta(id=tool_ids[event.index], args_json_chunk=delta.partial_json)
            elif delta.type == "thinking_delta" and event.index in opaque:
                opaque[event.index]["thinking"] = (
                    opaque[event.index].get("thinking", "") + delta.thinking
                )
            elif delta.type == "signature_delta" and event.index in opaque:
                opaque[event.index]["signature"] = delta.signature
        elif kind == "content_block_stop" and event.index in tool_ids:
            yield ToolCallEnd(id=tool_ids.pop(event.index))
        elif kind == "content_block_stop" and event.index in opaque:
            yield OpaqueBlock(provider=AnthropicProvider.name, data=opaque.pop(event.index))
        elif kind == "message_delta":
            reason = _STOP.get(event.delta.stop_reason or "end_turn", "end")
            usage = _usage(event.usage, usage)
    yield usage
    yield Stop(reason=reason)


def _usage(raw: Any, previous: Usage) -> Usage:
    """Anthropic `input_tokens` excludes cache reads and writes; our `input` includes reads."""
    fresh = getattr(raw, "input_tokens", None)
    read = getattr(raw, "cache_read_input_tokens", None)
    write = getattr(raw, "cache_creation_input_tokens", None)
    output = getattr(raw, "output_tokens", None)
    cached_read = read if read is not None else previous.cached_read
    base = fresh if fresh is not None else previous.input - previous.cached_read
    return Usage(
        input=base + cached_read,
        output=output if output is not None else previous.output,
        cached_read=cached_read,
        cached_write=write if write is not None else previous.cached_write,
    )


def _error_message(exc: anthropic.APIStatusError) -> str:
    body = exc.body if isinstance(exc.body, dict) else {}
    error = body.get("error") if isinstance(body.get("error"), dict) else {}
    return str(error.get("message") or exc.message)


__all__ = ["AnthropicProvider", "build_payload"]
