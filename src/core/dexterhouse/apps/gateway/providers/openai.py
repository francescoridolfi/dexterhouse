# SPDX-License-Identifier: AGPL-3.0-or-later
"""`openai` and `openai-compatible`: Chat Completions streaming through the official SDK.

`openai-compatible` covers vLLM, LM Studio, Groq, OpenRouter...: same wire format, a
`base_url` from the profile (or `OPENAI_COMPATIBLE_BASE_URL`) and `max_tokens` instead of
`max_completion_tokens`. OpenAI caches prefixes automatically: nothing to mark.
"""

import json
import re
from collections.abc import Iterator
from typing import Any

import openai

from dexterhouse.apps.gateway.conf import get_gateway_env
from dexterhouse.apps.gateway.messages import (
    CompletionRequest,
    ImagePart,
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

_STOP: dict[str, StopReason] = {
    "stop": "end",
    "tool_calls": "tool_use",
    "function_call": "tool_use",
    "length": "max_tokens",
    "content_filter": "refusal",
}
# Reasoning models accept only the default temperature.
_FIXED_TEMPERATURE = re.compile(r"^(o\d|gpt-5)")


class OpenAIProvider:
    name = "openai"
    max_tokens_field = "max_completion_tokens"

    def __init__(self, config: ProviderConfig | None = None) -> None:
        self.config = config or ProviderConfig()
        api_key, base_url = self._endpoint()
        self.client = openai.OpenAI(
            api_key=api_key or "missing",
            base_url=base_url or None,
            max_retries=0,
            timeout=self.config.timeout_s or get_gateway_env().GATEWAY_TIMEOUT_S,
            http_client=self.config.http_client,
        )

    def _endpoint(self) -> tuple[str, str]:
        env = get_gateway_env()
        return (
            self.config.api_key or env.OPENAI_API_KEY,
            self.config.base_url or env.OPENAI_BASE_URL,
        )

    def capabilities(self) -> Capabilities:
        return Capabilities(tools=True, vision=True, max_context=400_000)

    def build_payload(self, request: CompletionRequest) -> dict[str, Any]:
        """The Chat Completions body for `request` (public for the contract tests)."""
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [m for message in request.messages for m in _messages(message)],
            self.max_tokens_field: request.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if not (self.name == "openai" and _FIXED_TEMPERATURE.match(request.model)):
            payload["temperature"] = request.temperature
        if request.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": wire_tool_name(t.name),
                        "description": t.description,
                        "parameters": t.input_schema,
                    },
                }
                for t in request.tools
            ]
        return payload

    def stream(self, request: CompletionRequest) -> Iterator[StreamEvent]:
        try:
            chunks = self.client.chat.completions.create(**self.build_payload(request))
            yield from _translate(chunks)
        except openai.APIStatusError as exc:
            raise classify_http_error(
                exc.status_code, _error_message(exc), exc.response.headers
            ) from exc
        except openai.APITimeoutError as exc:
            raise ProviderError(str(exc), status="timeout", retryable=True) from exc
        except openai.APIConnectionError as exc:
            raise ProviderError(str(exc), retryable=True) from exc


class OpenAICompatibleProvider(OpenAIProvider):
    name = "openai-compatible"
    max_tokens_field = "max_tokens"

    def _endpoint(self) -> tuple[str, str]:
        env = get_gateway_env()
        base_url = self.config.base_url or env.OPENAI_COMPATIBLE_BASE_URL
        if not base_url:
            raise ProviderError("openai-compatible requires a base_url", code="configuration")
        return self.config.api_key or env.OPENAI_COMPATIBLE_API_KEY, base_url

    def capabilities(self) -> Capabilities:
        options = self.config.options
        return Capabilities(
            tools=bool(options.get("tools", True)),
            vision=bool(options.get("vision", False)),
            max_context=int(options.get("max_context", 32_000)),
            local=bool(options.get("is_local", False)),
        )


def _messages(message: Any) -> list[dict[str, Any]]:
    if message.role == "tool":
        return [
            {
                "role": "tool",
                "tool_call_id": part.call_id,
                "content": f"ERROR: {part.content}" if part.is_error else part.content,
            }
            for part in message.parts
            if isinstance(part, ToolResultPart)
        ]
    if message.role == "assistant":
        calls = [p for p in message.parts if isinstance(p, ToolCallPart)]
        out: dict[str, Any] = {"role": "assistant", "content": message.text() or None}
        if calls:
            out["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": wire_tool_name(c.name), "arguments": json.dumps(c.args)},
                }
                for c in calls
            ]
        return [out]
    images = [p for p in message.parts if isinstance(p, ImagePart)]
    if not images:
        return [{"role": message.role, "content": message.text()}]
    content: list[dict[str, Any]] = [
        {"type": "text", "text": p.text} for p in message.parts if isinstance(p, TextPart)
    ]
    content += [
        {"type": "image_url", "image_url": {"url": f"data:{p.media_type};base64,{p.data}"}}
        for p in images
    ]
    return [{"role": message.role, "content": content}]


def _translate(chunks: Any) -> Iterator[StreamEvent]:
    open_calls: dict[int, str] = {}
    usage = Usage()
    reason: StopReason = "end"
    for chunk in chunks:
        if chunk.usage is not None:
            details = getattr(chunk.usage, "prompt_tokens_details", None)
            usage = Usage(
                input=chunk.usage.prompt_tokens or 0,
                output=chunk.usage.completion_tokens or 0,
                cached_read=getattr(details, "cached_tokens", 0) or 0,
            )
        for choice in chunk.choices:
            delta = choice.delta
            if delta is not None:
                if delta.content:
                    yield TextDelta(text=delta.content)
                if getattr(delta, "refusal", None):
                    reason = "refusal"
                for call in delta.tool_calls or []:
                    if call.index not in open_calls:
                        call_id = call.id or f"call_{call.index}"
                        open_calls[call.index] = call_id
                        name = call.function.name if call.function else ""
                        yield ToolCallStart(id=call_id, name=internal_tool_name(name or ""))
                    if call.function and call.function.arguments:
                        yield ToolCallDelta(
                            id=open_calls[call.index], args_json_chunk=call.function.arguments
                        )
            if choice.finish_reason:
                reason = (
                    "refusal" if reason == "refusal" else _STOP.get(choice.finish_reason, "end")
                )
    for call_id in open_calls.values():
        yield ToolCallEnd(id=call_id)
    yield usage
    yield Stop(reason=reason)


def _error_message(exc: openai.APIStatusError) -> str:
    body = exc.body if isinstance(exc.body, dict) else {}
    error = body.get("error", body) if isinstance(body.get("error", body), dict) else {}
    code = error.get("code") or ""
    message = str(error.get("message") or exc.message)
    return f"{code}: {message}" if code else message
