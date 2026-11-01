# SPDX-License-Identifier: AGPL-3.0-or-later
"""Configuration, errors, path confinement and output limits shared by the tools."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

#: Inline output limit of every tool (contracts/tools/README.md).
OUTPUT_LIMIT = 64 * 1024
#: Full output handed back to the runner (`artifact_payload`) when the inline one is cut.
FULL_OUTPUT_LIMIT = 4 * 1024 * 1024
IGNORED_DIRS = frozenset({".git", "node_modules", ".venv", "__pycache__", ".mypy_cache"})
#: `env` keys an agent may pass to `exec`, besides the stack's own (workspace.md).
ENV_ALLOWLIST = frozenset({"PYTHONDONTWRITEBYTECODE", "CI", "NODE_ENV", "DJANGO_SETTINGS_MODULE"})
_UNITS = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}


class ToolFailure(Exception):  # noqa: N818 - a tool outcome, not a bug
    def __init__(self, code: str, detail: str, **data: Any) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.data = data

    def as_dict(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "detail": self.detail}, **self.data}


def parse_size(value: str) -> int:
    """`5G`, `512m`, `1024` -> bytes."""
    text = value.strip().lower().removesuffix("b")
    unit = text[-1] if text and text[-1] in _UNITS else ""
    return int(float(text[: len(text) - len(unit)] or 0) * _UNITS[unit])


@dataclass(frozen=True)
class Config:
    root: Path
    quota_bytes: int = 5 * 1024**3
    test_command: str = ""
    lint_command: str = ""
    stack_env_keys: frozenset[str] = frozenset()
    services: list[dict[str, Any]] = field(default_factory=list)
    exec_timeout_s: int = 120
    test_timeout_s: int = 900

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Config":
        env = dict(os.environ if env is None else env)
        return cls(
            root=Path(env.get("DH_WORKSPACE_ROOT", "/workspace")),
            quota_bytes=parse_size(env.get("DH_WORKSPACE_QUOTA", "5G")),
            test_command=env.get("DH_TEST_COMMAND", ""),
            lint_command=env.get("DH_LINT_COMMAND", ""),
            stack_env_keys=frozenset(k for k in env.get("DH_STACK_ENV_KEYS", "").split(",") if k),
            services=json.loads(env.get("DH_SERVICES", "[]")),
            exec_timeout_s=int(env.get("DH_EXEC_TIMEOUT_S", "120")),
            test_timeout_s=int(env.get("DH_TEST_TIMEOUT_S", "900")),
        )


def resolve(root: Path, path: str, *, write: bool = False) -> Path:
    """The absolute path of `path` inside `root`, or `workspace_escape`."""
    if not isinstance(path, str) or not path or "\x00" in path:
        raise ToolFailure("workspace_escape", "a relative path is required")
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts:
        raise ToolFailure("workspace_escape", f"{path}: absolute paths and '..' are refused")
    if write and pure.parts and pure.parts[0] == ".git":
        raise ToolFailure("workspace_escape", f"{path}: .git/ is managed by the system")
    base = root.resolve()
    target = (base / pure).resolve()
    if target != base and not target.is_relative_to(base):
        raise ToolFailure("workspace_escape", f"{path}: resolves outside the workspace")
    if write and target.is_relative_to(base / ".git"):
        raise ToolFailure("workspace_escape", f"{path}: .git/ is managed by the system")
    return target


def relative(root: Path, target: Path) -> str:
    return target.relative_to(root.resolve()).as_posix() or "."


def clip(text: str, limit: int = OUTPUT_LIMIT) -> tuple[str, bool]:
    """Cut `text` to `limit` UTF-8 bytes; returns (text, truncated)."""
    raw = text.encode()
    if len(raw) <= limit:
        return text, False
    return raw[:limit].decode(errors="ignore"), True


def usage_bytes(root: Path) -> int:
    """Disk used under `root` (allocated blocks, so sparse and preallocated files count)."""
    total = 0
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        stat = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    total += getattr(stat, "st_blocks", 0) * 512 or stat.st_size
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
        except OSError:
            continue
    return total


def human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"  # pragma: no cover
