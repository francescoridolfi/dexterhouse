# SPDX-License-Identifier: AGPL-3.0-or-later
"""Internal, provider-neutral format (infra/llm_gateway_detail.md).

No provider detail leaves the gateway: the agents runtime only sees these models and the
streaming events below.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Profile = Literal["strong", "balanced", "fast", "embed"]
StopReason = Literal["end", "tool_use", "max_tokens", "refusal"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TextPart(_Model):
    kind: Literal["text"] = "text"
    text: str


class ToolCallPart(_Model):
    kind: Literal["tool_call"] = "tool_call"
    id: str
    name: str
    args: dict[str, Any]


class ToolResultPart(_Model):
    kind: Literal["tool_result"] = "tool_result"
    call_id: str
    content: str
    is_error: bool = False


class ImagePart(_Model):
    kind: Literal["image"] = "image"
    media_type: str
    data: str  # base64


Part = Annotated[TextPart | ToolCallPart | ToolResultPart | ImagePart, Field(discriminator="kind")]


class Message(_Model):
    role: Literal["system", "user", "assistant", "tool"]
    parts: list[Part]
    cache_breakpoint: bool = False  # end of the stable prefix

    def text(self) -> str:
        return "".join(part.text for part in self.parts if isinstance(part, TextPart))


class ToolSpec(_Model):
    name: str
    description: str
    input_schema: dict[str, Any]


class CompletionRequest(_Model):
    messages: list[Message]
    tools: list[ToolSpec] = Field(default_factory=list)
    profile: Profile
    model: str
    max_tokens: int = Field(gt=0)
    temperature: float = 0.2
    metadata: dict[str, Any] = Field(default_factory=dict)  # project_id, agent_turn_id, trace_id


# Streaming events -------------------------------------------------------------------------


class TextDelta(_Model):
    kind: Literal["text_delta"] = "text_delta"
    text: str


class ToolCallStart(_Model):
    kind: Literal["tool_call_start"] = "tool_call_start"
    id: str
    name: str


class ToolCallDelta(_Model):
    kind: Literal["tool_call_delta"] = "tool_call_delta"
    id: str
    args_json_chunk: str


class ToolCallEnd(_Model):
    kind: Literal["tool_call_end"] = "tool_call_end"
    id: str


class Usage(_Model):
    kind: Literal["usage"] = "usage"
    input: int = 0  # includes cached_read
    output: int = 0
    cached_read: int = 0
    cached_write: int = 0


class Stop(_Model):
    kind: Literal["stop"] = "stop"
    reason: StopReason


StreamEvent = TextDelta | ToolCallStart | ToolCallDelta | ToolCallEnd | Usage | Stop


class CompletionResult(_Model):
    """A whole response, aggregated from the stream."""

    message: Message
    usage: Usage
    stop_reason: StopReason
    provider: str
    model: str
