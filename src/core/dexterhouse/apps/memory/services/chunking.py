# SPDX-License-Identifier: AGPL-3.0-or-later
"""Split artifacts into chunks: Markdown by heading, structured kinds by top-level item."""

import json
import re
from dataclasses import dataclass
from typing import Any

MAX_CHARS = 1800  # ~500 tokens: a chunk fits the memory section of even the `fast` profile
_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*#*\s*$")


@dataclass(frozen=True)
class Chunk:
    heading: str
    content: str


def chunk_markdown(text: str, max_chars: int = MAX_CHARS) -> list[Chunk]:
    """One chunk per heading section (`#`..`###`); long sections split at paragraphs."""
    sections: list[tuple[str, list[str]]] = [("", [])]
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        match = None if in_fence else _HEADING.match(line)
        if match:
            sections.append((match[2][:200], [line]))
        else:
            sections[-1][1].append(line)
    chunks: list[Chunk] = []
    for heading, lines in sections:
        body = "\n".join(lines).strip()
        if body:
            chunks += [Chunk(heading, part) for part in _split(body, max_chars)]
    return chunks


def chunk_structured(data: Any, max_chars: int = MAX_CHARS) -> list[Chunk]:
    """Structured artifacts: one piece per top-level key or list item, merged up to the limit."""
    pieces: list[Chunk] = []
    items = data.items() if isinstance(data, dict) else [("items", data)]
    for key, value in items:
        if isinstance(value, list) and value:
            for index, item in enumerate(value):
                pieces.append(Chunk(f"{key}[{index}]", f"{key}[{index}]: {_dump(item)}"))
        else:
            pieces.append(Chunk(str(key), f"{key}: {_dump(value)}"))
    merged: list[Chunk] = []
    for piece in pieces:
        if merged and len(merged[-1].content) + len(piece.content) + 1 <= max_chars:
            last = merged.pop()
            merged.append(Chunk(last.heading, f"{last.content}\n{piece.content}"))
        else:
            merged += [Chunk(piece.heading, part) for part in _split(piece.content, max_chars)]
    return merged


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _split(text: str, max_chars: int) -> list[str]:
    """Greedy paragraph packing; a paragraph longer than the limit is cut hard."""
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    current = ""
    for paragraph in re.split(r"\n\s*\n", text):
        while len(paragraph) > max_chars:
            if current:
                parts.append(current)
                current = ""
            parts.append(paragraph[:max_chars])
            paragraph = paragraph[max_chars:]
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) > max_chars:
            parts.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        parts.append(current)
    return [p for p in parts if p.strip()]
