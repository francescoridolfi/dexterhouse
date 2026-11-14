# SPDX-License-Identifier: AGPL-3.0-or-later
"""The source files of the workspace and their language."""

import os
import subprocess  # nosec B404 - git ls-files on the workspace
from pathlib import Path, PurePosixPath

#: Directories never analysed: VCS, dependencies, virtualenvs, caches and build outputs.
EXCLUDED_DIRS = frozenset(
    ".git .hg .svn node_modules bower_components vendor .venv venv env .env .tox .nox "
    "__pycache__ .mypy_cache .pytest_cache .ruff_cache site-packages build dist out target "
    ".next .nuxt .svelte-kit .turbo .cache coverage htmlcov .gradle .idea .vscode "
    "graphify-out".split()
)
LANGUAGES = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".go": "go",
    ".java": "java",
}
_LS_FILES = ("ls-files", "-z", "--cached", "--others", "--exclude-standard")
MAX_FILE_BYTES = 1024 * 1024
MAX_FILES = 5000


def language(path: str) -> str | None:
    name = path.rsplit("/", 1)[-1]
    if name.endswith((".min.js", ".d.ts", ".bundle.js")):
        return None
    return LANGUAGES.get(PurePosixPath(name).suffix.lower())


def _excluded(path: str) -> bool:
    return any(part in EXCLUDED_DIRS for part in PurePosixPath(path).parts[:-1])


def _git_files(root: Path) -> list[str] | None:
    if not (root / ".git").exists():
        return None
    try:
        done = subprocess.run(  # noqa: S603  # nosec B603 B607 - fixed git argv, no shell
            ["git", "-C", str(root), *_LS_FILES],  # noqa: S607
            capture_output=True,
            timeout=30,
            check=False,
            env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if done.returncode != 0:
        return None
    return sorted({p for p in done.stdout.decode("utf-8", "replace").split("\x00") if p})


def _walk_files(root: Path) -> list[str]:
    found: list[str] = []
    for folder, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS)
        base = Path(folder).relative_to(root)
        found += [(base / n).as_posix() for n in sorted(names)]
    return found


def source_files(root: Path) -> list[tuple[str, str]]:
    """(relative path, language) of the files to analyse, sorted, at most `MAX_FILES`."""
    root = root.resolve()
    listed = _git_files(root)
    candidates = listed if listed is not None else _walk_files(root)
    out: list[tuple[str, str]] = []
    for path in candidates:
        lang = language(path)
        if lang is None or _excluded(path):
            continue
        file = root / path
        try:
            if file.is_symlink() or not file.is_file() or file.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        out.append((path, lang))
        if len(out) >= MAX_FILES:
            break
    return out
