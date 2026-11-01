# SPDX-License-Identifier: AGPL-3.0-or-later
"""`ollama`: local models over the HTTP API (`/api/chat`, NDJSON streaming).

Ollama returns each tool call whole and may omit its id: the gateway assigns `call_<n>`.
"""

import json
from collections.abc import Iterator
from typing import Any

import httpx2

from dexterhouse.apps.gateway.conf import get_gateway_env
from dexterhouse.apps.gateway.messages import (
    CompletionRequest,
    ImagePart,
    Stop,
    StopReason,
    StreamEvent,
    TextDelta,
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


def ollama_client(config: ProviderConfig) -> httpx2.Client:
    """HTTP client for the configured Ollama (shared with the embedder)."""
    if config.http_client is not None:
        return config.http_client
    env = get_gateway_env()
    return httpx2.Client(
        base_url=config.base_url or env.OLLAMA_BASE_URL,
        timeout=config.timeout_s or env.GATEWAY_TIMEOUT_S,
    )


class OllamaProvider:
    name = "ollama"

    def __init__(self, config: ProviderConfig | None = None) -> None:
        self.config = config or ProviderConfig()
        self.client = ollama_client(self.config)

    def capabilities(self) -> Capabilities:
        options = self.config.options
        return Capabilities(
            tools=bool(options.get("tools", True)),
            vision=bool(options.get("vision", False)),
            max_context=int(options.get("max_context", 32_000)),
            local=True,
        )

    def build_payload(self, request: CompletionRequest) -> dict[str, Any]:
        """The `/api/chat` body for `request` (public for the contract tests)."""
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [m for message in request.messages for m in _messages(message)],
            "stream": True,
            "options": {"temperature": request.temperature, "num_predict": request.max_tokens},
        }
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
            with self.client.stream(
                "POST", "/api/chat", json=self.build_payload(request)
            ) as response:
                if response.status_code >= 400:
                    response.read()
                    raise classify_http_error(
                        response.status_code, _error_text(response.text), response.headers
                    )
                yield from _translate(response.iter_lines())
        except httpx2.TimeoutException as exc:
            raise ProviderError(str(exc), status="timeout", retryable=True) from exc
        except httpx2.TransportError as exc:
            raise ProviderError(f"ollama unreachable: {exc}", retryable=True) from exc


def _messages(message: Any) -> list[dict[str, Any]]:
    if message.role == "tool":
        return [
            {"role": "tool", "content": f"ERROR: {p.content}" if p.is_error else p.content}
            for p in message.parts
            if isinstance(p, ToolResultPart)
        ]
    out: dict[str, Any] = {"role": message.role, "content": message.text()}
    images = [p.data for p in message.parts if isinstance(p, ImagePart)]
    if images:
        out["images"] = images
    calls = [p for p in message.parts if isinstance(p, ToolCallPart)]
    if calls:
        out["tool_calls"] = [
            {"function": {"name": wire_tool_name(c.name), "arguments": c.args}} for c in calls
        ]
    return [out]


def _translate(lines: Iterator[str]) -> Iterator[StreamEvent]:
    count = 0
    usage = Usage()
    reason: StopReason = "end"
    for line in lines:
        if not line.strip():
            continue
        data = json.loads(line)
        if "error" in data:
            raise ProviderError(f"ollama: {data['error']}", retryable=True)
        message = data.get("message") or {}
        if message.get("content"):
            yield TextDelta(text=message["content"])
        for call in message.get("tool_calls") or []:
            count += 1
            function = call.get("function") or {}
            call_id = call.get("id") or f"call_{count}"
            yield ToolCallStart(id=call_id, name=internal_tool_name(function.get("name", "")))
            yield ToolCallDelta(
                id=call_id, args_json_chunk=json.dumps(function.get("arguments") or {})
            )
            yield ToolCallEnd(id=call_id)
        if data.get("done"):
            usage = Usage(input=data.get("prompt_eval_count", 0), output=data.get("eval_count", 0))
            reason = "max_tokens" if data.get("done_reason") == "length" else "end"
    yield usage
    yield Stop(reason="tool_use" if count and reason == "end" else reason)


def _error_text(body: str) -> str:
    try:
        return str(json.loads(body).get("error", body))
    except (json.JSONDecodeError, AttributeError):
        return body
