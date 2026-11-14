# SPDX-License-Identifier: AGPL-3.0-or-later
"""Estimate the prompt-cache writes of an `anthropic-cli` turn of N steps, before and after
the block transcript (ADR-0017).

Cache model (Anthropic prompt caching): entries are written at breakpoints and keyed by the
exact prefix up to a block boundary; a request reads the longest cached prefix ending at one
of the 20 blocks before its last breakpoint and writes everything after it. The CLI puts a
breakpoint on the system prompt and on the last block of the last message.

Run: `uv run python -m tests.gateway.cli_cache_estimate [steps]` from `src/core`.
Defaults mirror developer turn T-01 of the termcalc run (6k cached system prefix, a 14k
context message, ~650 tokens per step).
"""

import json
import sys
from dataclasses import dataclass

from dexterhouse.apps.gateway.messages import (
    CompletionRequest,
    Message,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)
from dexterhouse.apps.gateway.providers.anthropic_cli import TOOL_PREFIX, transcript
from dexterhouse.apps.gateway.providers.base import wire_tool_name

CHARS_PER_TOKEN = 3.6
LOOKBACK = 20
#: USD per million tokens (prices.yaml): (cache write, cache read).
PRICES = {"opus": (5.00, 0.20), "sonnet": (2.50, 0.20)}


@dataclass(frozen=True)
class Shape:
    steps: int = 18
    system: int = 6000
    context: int = 14000
    call: int = 150
    result: int = 500


def legacy_transcript(request: CompletionRequest) -> list[dict[str, str]]:
    """The transcript before the fix: one block, closed by a variable trailer."""
    turns = [m for m in request.messages if m.role != "system"]
    if len(turns) == 1:
        return [{"type": "text", "text": turns[0].text()}]
    lines = ["<conversation>"]
    for message in turns:
        lines.append(f"[{message.role}]")
        for part in message.parts:
            if isinstance(part, ToolCallPart):
                name = TOOL_PREFIX + wire_tool_name(part.name)
                lines.append(f"[tool call {part.id}] {name} {json.dumps(part.args)}")
            elif isinstance(part, ToolResultPart):
                lines.append(f"[tool result {part.call_id}]\n{part.content}")
            elif hasattr(part, "text"):
                lines.append(part.text)
    lines += ["</conversation>", "Continue as the assistant: call a tool if needed."]
    return [{"type": "text", "text": "\n".join(lines)}]


def _filler(tokens: int, seed: str) -> str:
    return (seed + " ") * int(tokens * CHARS_PER_TOKEN / (len(seed) + 1))


def requests(shape: Shape) -> list[CompletionRequest]:
    messages = [
        Message(role="system", parts=[TextPart(text=_filler(shape.system, "system"))]),
        Message(role="user", parts=[TextPart(text=_filler(shape.context, "context"))]),
    ]
    out = []
    for step in range(shape.steps):
        out.append(
            CompletionRequest(messages=list(messages), profile="strong", model="m", max_tokens=8000)
        )
        call = f"c{step}"
        messages += [
            Message(
                role="assistant",
                parts=[
                    ToolCallPart(
                        id=call, name="workspace.read", args={"p": _filler(shape.call, f"a{step}")}
                    )
                ],
            ),
            Message(
                role="tool",
                parts=[ToolResultPart(call_id=call, content=_filler(shape.result, f"r{step}"))],
            ),
        ]
    return out


def simulate(blocks_per_request: list[list[str]]) -> tuple[list[int], list[int]]:
    """Cache writes and reads of each request's messages (the system prompt is always read
    from the cache in both versions, so it is left out)."""
    cache: set[tuple[str, ...]] = set()
    writes, reads = [], []
    for blocks in blocks_per_request:
        sizes = [len(b) / CHARS_PER_TOKEN for b in blocks]
        last = len(blocks)
        hit = 0
        for end in range(last, max(last - LOOKBACK, 0) - 1, -1):
            if tuple(blocks[:end]) in cache:
                hit = end
                break
        writes.append(round(sum(sizes[hit:])))
        reads.append(round(sum(sizes[:hit])))
        cache.add(tuple(blocks))
    return writes, reads


def estimate(shape: Shape) -> dict[str, tuple[list[int], list[int]]]:
    reqs = requests(shape)
    return {
        name: simulate([[b["text"] for b in render(r)] for r in reqs])
        for name, render in (("before", legacy_transcript), ("after", transcript))
    }


def main(argv: list[str]) -> None:
    shape = Shape(steps=int(argv[0])) if argv else Shape()
    lines = [
        f"{shape.steps} steps, {shape.context} context tokens, "
        f"{shape.call + shape.result} tokens per step",
        "| | cache writes | cache reads | Opus 5.5 USD | Sonnet 5.5 USD |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, (writes, reads) in estimate(shape).items():
        w, r = sum(writes), sum(reads)
        usd = {k: (w * pw + r * pr) / 1e6 for k, (pw, pr) in PRICES.items()}
        lines.append(f"| {name} | {w:,} | {r:,} | {usd['opus']:.2f} | {usd['sonnet']:.2f} |")
    sys.stdout.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
