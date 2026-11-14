# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-file facts, cached by SHA-256 of the content (in memory and under `.git/`).

The disk cache (`.git/dexterhouse/code-graph-cache.json`) survives MCP server restarts and
is never committed; a change of :data:`FACTS_VERSION` drops it. Only changed files are
parsed again, so a rebuild after a commit costs one read and one hash per file.
"""

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dexterhouse_runner.workspace_mcp.graph.lang_python import python_facts
from dexterhouse_runner.workspace_mcp.graph.lang_regex import go_facts, java_facts, js_facts

FACTS_VERSION = 1
CACHE_FILE = Path(".git") / "dexterhouse" / "code-graph-cache.json"
EXTRACTORS: dict[str, Callable[[str], dict[str, Any]]] = {
    "python": python_facts,
    "javascript": js_facts,
    "typescript": js_facts,
    "go": go_facts,
    "java": java_facts,
}
_MEMORY: dict[str, dict[str, Any]] = {}


def _load(root: Path) -> dict[str, Any]:
    key = str(root)
    if key not in _MEMORY:
        cached: dict[str, Any] = {}
        try:
            raw = json.loads((root / CACHE_FILE).read_text("utf-8"))
            if raw.get("version") == FACTS_VERSION:
                cached = raw.get("files", {})
        except (OSError, ValueError, AttributeError):
            cached = {}
        _MEMORY[key] = cached
    return _MEMORY[key]


def _save(root: Path, cache: dict[str, Any]) -> None:
    target = root / CACHE_FILE
    if not target.parent.parent.is_dir():  # no .git: memory only
        return
    try:
        target.parent.mkdir(exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": FACTS_VERSION, "files": cache}), "utf-8")
        os.replace(tmp, target)
    except OSError:
        return


def collect(root: Path, files: list[tuple[str, str]]) -> tuple[dict[str, dict[str, Any]], int]:
    """{path: facts} for `files`, and how many files were parsed (cache misses)."""
    root = root.resolve()
    cache = _load(root)
    out: dict[str, dict[str, Any]] = {}
    parsed = 0
    for path, lang in files:
        try:
            raw = (root / path).read_bytes()
        except OSError:
            continue
        digest = hashlib.sha256(raw).hexdigest()
        entry = cache.get(path)
        if entry is None or entry.get("sha") != digest or entry.get("lang") != lang:
            text = raw.decode("utf-8", errors="replace")
            entry = {"sha": digest, "lang": lang, "facts": EXTRACTORS[lang](text)}
            cache[path] = entry
            parsed += 1
        out[path] = entry["facts"]
    stale = set(cache) - set(out)
    for path in stale:
        del cache[path]
    if parsed or stale:
        _save(root, cache)
    return out, parsed


def clear_memory() -> None:
    _MEMORY.clear()
