# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deterministic provider for tests and CI: never calls the network (testing.md).

Responses come from a script (or a JSON cassette with `{"responses": [...]}`) and are served
in order; without a script, or once it is exhausted, a *responder* answers: the callable named
by `settings.GATEWAY_FAKE_RESPONDER` (`request -> FakeResponse`, used by end-to-end tests and
demos), else the provider echoes the last user text.
"""

import json
import math
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Literal

from django.conf import settings
from django.utils.module_loading import import_string
from pydantic import BaseModel, ConfigDict, Field

from dexterhouse.apps.gateway.messages import (
    CompletionRequest,
    Stop,
    StopReason,
    StreamEvent,
    TextDelta,
    ToolCallDelta,
    ToolCallEnd,
    ToolCallStart,
    Usage,
)
from dexterhouse.apps.gateway.providers.base import Capabilities, ProviderError

CHARS_PER_TOKEN = 3.5
CHUNK = 16


class FakeToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class FakeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = ""
    tool_calls: list[FakeToolCall] = Field(default_factory=list)
    usage: Usage | None = None
    stop: StopReason | None = None
    error: Literal["error", "rate_limited", "timeout"] | None = None
    error_code: str = "provider"


def estimate_tokens(text: str) -> int:
    """Heuristic used when the provider has no tokenizer: `chars / 3.5`."""
    return math.ceil(len(text) / CHARS_PER_TOKEN) if text else 0


Responder = Callable[[CompletionRequest], FakeResponse]


def configured_responder() -> Responder | None:
    path = getattr(settings, "GATEWAY_FAKE_RESPONDER", "")
    return import_string(path) if path else None


class FakeProvider:
    name = "fake"

    def __init__(
        self, responses: list[FakeResponse] | None = None, responder: Responder | None = None
    ) -> None:
        self.responses = list(responses or [])
        self.responder = responder
        self.requests: list[CompletionRequest] = []

    def capabilities(self) -> Capabilities:
        return Capabilities(local=True)

    @classmethod
    def from_cassette(cls, path: Path) -> "FakeProvider":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls([FakeResponse.model_validate(item) for item in data["responses"]])

    def stream(self, request: CompletionRequest) -> Iterator[StreamEvent]:
        self.requests.append(request)
        if self.responses:
            response = self.responses.pop(0)
        else:
            response = (self.responder or self._echo)(request)
        if response.error:
            raise ProviderError(
                f"fake {response.error}",
                status=response.error,
                code=response.error_code,
                retryable=response.error_code == "provider",
            )
        for start in range(0, len(response.text), CHUNK):
            yield TextDelta(text=response.text[start : start + CHUNK])
        for call in response.tool_calls:
            yield ToolCallStart(id=call.id, name=call.name)
            yield ToolCallDelta(id=call.id, args_json_chunk=json.dumps(call.args))
            yield ToolCallEnd(id=call.id)
        yield response.usage or Usage(
            input=sum(estimate_tokens(m.text()) for m in request.messages),
            output=estimate_tokens(response.text),
        )
        yield Stop(reason=response.stop or ("tool_use" if response.tool_calls else "end"))

    @staticmethod
    def _echo(request: CompletionRequest) -> FakeResponse:
        last_user = next((m.text() for m in reversed(request.messages) if m.role == "user"), "")
        return FakeResponse(text=f"fake: {last_user}")
