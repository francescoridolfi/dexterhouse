# SPDX-License-Identifier: AGPL-3.0-or-later
"""The provider protocol and the stream aggregator shared by every provider."""

import json
from collections.abc import Iterable, Iterator
from typing import Protocol, runtime_checkable

from dexterhouse.apps.gateway.messages import (
    CompletionRequest,
    CompletionResult,
    Message,
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


class ProviderError(RuntimeError):
    """A provider call failed; `status` maps to `LLMCall.status`."""

    def __init__(self, message: str, *, status: str = "error") -> None:
        super().__init__(message)
        self.status = status


@runtime_checkable
class Provider(Protocol):
    """A concrete LLM backend translating the internal format to its API."""

    name: str

    def stream(self, request: CompletionRequest) -> Iterator[StreamEvent]:
        """Yield streaming events ending with `Usage` and `Stop`."""
        ...


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
