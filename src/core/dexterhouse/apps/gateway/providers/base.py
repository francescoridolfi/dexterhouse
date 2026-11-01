# SPDX-License-Identifier: AGPL-3.0-or-later
"""The provider protocol, shared errors and the stream aggregator used by every provider."""

import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from dexterhouse.apps.gateway.messages import (
    CompletionRequest,
    CompletionResult,
    Message,
    OpaqueBlock,
    OpaquePart,
    Part,
    Stop,
    StopReason,
    StreamEvent,
    TextDelta,
    TextPart,
    ToolCallDelta,
    ToolCallEnd,
    ToolCallPart,
    ToolCallStart,
    Usage,
)

RETRY_AFTER_MAX_S = 60.0


class ProviderError(RuntimeError):
    """A provider call failed.

    `status` maps to `LLMCall.status` (`error`, `rate_limited`, `timeout`); `code` is the
    gateway reason (`provider`, `context_length`, `authentication`, `configuration`,
    `unavailable`); `retryable` errors are retried with backoff by the gateway.
    """

    def __init__(
        self,
        message: str,
        *,
        status: str = "error",
        code: str = "provider",
        retryable: bool = False,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.retryable = retryable
        self.retry_after = retry_after


@dataclass(frozen=True)
class Capabilities:
    tools: bool = True
    vision: bool = False
    streaming: bool = True
    max_context: int = 128_000
    local: bool = False  # true: no data leaves the installation (`data_residency: local`)


@dataclass(frozen=True)
class ProviderConfig:
    """How to reach a provider; secrets come from the environment, never from the DB."""

    api_key: str = ""
    base_url: str = ""
    options: Mapping[str, Any] = field(default_factory=dict)
    http_client: Any = None  # httpx2.Client, injected by tests (recorded responses)
    timeout_s: float | None = None


@runtime_checkable
class Provider(Protocol):
    """A concrete LLM backend translating the internal format to its API."""

    name: str

    def stream(self, request: CompletionRequest) -> Iterator[StreamEvent]:
        """Yield streaming events ending with `Usage` and `Stop`."""
        ...

    def capabilities(self) -> Capabilities:
        """What the backend supports (tool use, vision, context size, locality)."""
        ...


# Tool names: our permission ids contain a dot (`memory.search`), which provider APIs reject
# (`^[a-zA-Z0-9_-]{1,64}$`). Ids never contain `__`, so the mapping is reversible.


def wire_tool_name(name: str) -> str:
    return name.replace(".", "__")


def internal_tool_name(name: str) -> str:
    return name.replace("__", ".")


def classify_http_error(
    status_code: int | None, message: str, headers: Mapping[str, str] | None = None
) -> ProviderError:
    """Map an HTTP failure to a `ProviderError` (llm_gateway_detail.md, errors table)."""
    lowered = message.lower()
    if status_code == 429:
        return ProviderError(
            message,
            status="rate_limited",
            retryable=True,
            retry_after=_retry_after(headers or {}),
        )
    if status_code == 408:
        return ProviderError(message, status="timeout", retryable=True)
    if status_code is not None and status_code >= 500:
        return ProviderError(message, retryable=True)
    if status_code in {401, 403}:
        return ProviderError(message, code="authentication")
    if any(
        hint in lowered
        for hint in ("context length", "context_length", "too long", "maximum context")
    ):
        return ProviderError(message, code="context_length")
    if status_code == 404:
        return ProviderError(message, code="configuration")
    return ProviderError(message)


def _retry_after(headers: Mapping[str, str]) -> float | None:
    raw = headers.get("retry-after") or headers.get("Retry-After")
    try:
        return min(float(raw), RETRY_AFTER_MAX_S) if raw is not None else None
    except ValueError:
        return None


def parse_args(raw: str) -> dict[str, object]:
    """Tolerant JSON parsing of tool arguments; invalid JSON becomes `{"_raw": raw}`."""
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {"_raw": raw}
    return value if isinstance(value, dict) else {"_value": value}


def collect(events: Iterable[StreamEvent], *, provider: str, model: str) -> CompletionResult:
    """Aggregate a stream into a single assistant message."""
    parts: list[Part] = []
    text: list[str] = []
    calls: dict[str, tuple[str, list[str]]] = {}
    usage = Usage()
    reason: StopReason = "end"

    def flush_text() -> None:
        if text:
            parts.append(TextPart(text="".join(text)))
            text.clear()

    for event in events:
        if isinstance(event, TextDelta):
            text.append(event.text)
        elif isinstance(event, ToolCallStart):
            flush_text()
            calls[event.id] = (event.name, [])
        elif isinstance(event, ToolCallDelta):
            calls[event.id][1].append(event.args_json_chunk)
        elif isinstance(event, ToolCallEnd):
            name, chunks = calls.pop(event.id)
            parts.append(ToolCallPart(id=event.id, name=name, args=parse_args("".join(chunks))))
        elif isinstance(event, OpaqueBlock):
            flush_text()
            parts.append(OpaquePart(provider=event.provider, data=event.data))
        elif isinstance(event, Usage):
            usage = event
        elif isinstance(event, Stop):
            reason = event.reason
    flush_text()
    return CompletionResult(
        message=Message(role="assistant", parts=parts),
        usage=usage,
        stop_reason=reason,
        provider=provider,
        model=model,
    )


def system_text(request: CompletionRequest) -> str:
    """All system messages joined, for providers with a single system string."""
    return "\n\n".join(m.text() for m in request.messages if m.role == "system")
