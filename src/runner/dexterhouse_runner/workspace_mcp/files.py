# SPDX-License-Identifier: AGPL-3.0-or-later
"""`workspace.list/read/search/write/edit/delete/move` (contracts/tools/workspace.md)."""

import fnmatch
import os
import re
import shutil
from pathlib import Path
from typing import Any

from dexterhouse_runner.workspace_mcp.base import (
    IGNORED_DIRS,
    OUTPUT_LIMIT,
    Config,
    ToolFailure,
    clip,
    human,
    relative,
    resolve,
    usage_bytes,
)

MAX_TREE_ENTRIES = 2000
MAX_SEARCH_FILE = 2 * 1024 * 1024


def _visible(name: str, include_hidden: bool) -> bool:
    return name not in IGNORED_DIRS and (include_hidden or not name.startswith("."))


def list_tree(cfg: Config, path: str = ".", depth: int = 2, include_hidden: bool = False) -> dict:
    base = resolve(cfg.root, path)
    if not base.is_dir():
        raise ToolFailure("invalid", f"{path}: not a directory")
    lines: list[str] = []
    count = 0
    truncated = False

    def walk(folder: Path, level: int) -> int:
        nonlocal count, truncated
        size_total = 0
        try:
            entries = sorted(os.scandir(folder), key=lambda e: (not e.is_dir(), e.name))
        except OSError:
            return 0
        for entry in entries:
            if not _visible(entry.name, include_hidden):
                continue
            if count >= MAX_TREE_ENTRIES:
                truncated = True
                return size_total
            count += 1
            indent = "  " * level
            if entry.is_dir(follow_symlinks=False):
                index = len(lines)
                lines.append(f"{indent}{entry.name}/")
                if level + 1 < depth:
                    size = walk(Path(entry.path), level + 1)
                    lines[index] = f"{indent}{entry.name}/ ({human(size)})"
                    size_total += size
            else:
                size = entry.stat(follow_symlinks=False).st_size
                size_total += size
                lines.append(f"{indent}{entry.name} ({human(size)})")
        return size_total

    walk(base, 0)
    tree, cut = clip("\n".join(lines))
    return {
        "path": relative(cfg.root, base),
        "tree": tree,
        "entries": count,
        "truncated": truncated or cut,
    }


def read(
    cfg: Config, path: str, start_line: int | None = None, end_line: int | None = None
) -> dict:
    target = resolve(cfg.root, path)
    if not target.is_file():
        raise ToolFailure("not_found", f"{path}: no such file")
    raw = target.read_bytes()
    if b"\x00" in raw[:8192]:
        return {"path": path, "encoding": "binary", "size": len(raw), "content": ""}
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines(keepends=True)
    if start_line or end_line:
        first = max((start_line or 1) - 1, 0)
        text = "".join(lines[first : end_line or len(lines)])
    content, truncated = clip(text)
    result: dict[str, Any] = {
        "path": path,
        "content": content,
        "total_lines": len(lines),
        "encoding": "utf-8",
        "truncated": truncated,
    }
    if truncated:
        result["hint"] = "over 64 KB: read again with start_line/end_line"
    return result


def search(
    cfg: Config, pattern: str, path: str = ".", glob: str | None = None, max_results: int = 100
) -> dict:
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        raise ToolFailure("args_policy", f"invalid regex: {exc}") from exc
    base = resolve(cfg.root, path)
    root = cfg.root.resolve()
    matches: list[dict[str, Any]] = []
    for folder, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRS)
        for name in sorted(files):
            file = Path(folder) / name
            rel = file.relative_to(root).as_posix()
            if glob and not (fnmatch.fnmatch(rel, glob) or fnmatch.fnmatch(name, glob)):
                continue
            try:
                if file.is_symlink() or file.stat().st_size > MAX_SEARCH_FILE:
                    continue
                lines = file.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for number, line in enumerate(lines, start=1):
                if regex.search(line):
                    context = lines[max(number - 2, 0) : number + 1]
                    matches.append(
                        {
                            "file": rel,
                            "line": number,
                            "text": line[:400],
                            "context": [c[:400] for c in context],
                        }
                    )
                    if len(matches) >= max_results:
                        return {"matches": matches, "truncated": True}
    return {"matches": matches, "truncated": False}


def _check_quota(cfg: Config, extra: int) -> None:
    used = usage_bytes(cfg.root)
    if used + extra > cfg.quota_bytes:
        raise ToolFailure(
            "quota_exceeded",
            f"workspace quota exceeded: {human(used)} used + {human(extra)} > "
            f"{human(cfg.quota_bytes)}",
        )


def write(cfg: Config, path: str, content: str, create_dirs: bool = True) -> dict:
    target = resolve(cfg.root, path, write=True)
    data = content.encode()
    _check_quota(cfg, len(data))
    if target.is_dir():
        raise ToolFailure("invalid", f"{path} is a directory")
    created = not target.exists()
    if create_dirs:
        target.parent.mkdir(parents=True, exist_ok=True)
    elif not target.parent.is_dir():
        raise ToolFailure("invalid", f"{path}: parent directory does not exist")
    target.write_bytes(data)
    return {"path": path, "bytes": len(data), "created": created}


def edit(cfg: Config, path: str, old: str, new: str, occurrences: int = 1) -> dict:
    target = resolve(cfg.root, path, write=True)
    if not target.is_file():
        raise ToolFailure("not_found", f"{path}: no such file")
    text = target.read_text(encoding="utf-8")
    found = text.count(old) if old else 0
    if found == 0:
        raise ToolFailure("invalid", f"{path}: `old` not found")
    if found != occurrences:
        raise ToolFailure("invalid", f"{path}: `old` occurs {found} times, expected {occurrences}")
    updated = text.replace(old, new)
    _check_quota(cfg, max(len(updated.encode()) - len(text.encode()), 0))
    target.write_text(updated, encoding="utf-8")
    return {"path": path, "replaced": found}


def delete(cfg: Config, path: str) -> dict:
    target = resolve(cfg.root, path, write=True)
    if target == cfg.root.resolve():
        raise ToolFailure("workspace_escape", "the workspace root cannot be deleted")
    if not target.exists() and not target.is_symlink():
        return {"path": path, "deleted": False}
    if target.is_dir() and not target.is_symlink():
        shutil.rmtree(target)
    else:
        target.unlink()
    return {"path": path, "deleted": True}


def move(cfg: Config, from_: str, to: str) -> dict:
    source = resolve(cfg.root, from_, write=True)
    target = resolve(cfg.root, to, write=True)
    if not source.exists():
        raise ToolFailure("not_found", f"{from_}: no such file")
    if target.exists():
        raise ToolFailure("conflict", f"{to} already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    source.rename(target)
    return {"from": from_, "to": to}


__all__ = ["OUTPUT_LIMIT", "delete", "edit", "list_tree", "move", "read", "search", "write"]
