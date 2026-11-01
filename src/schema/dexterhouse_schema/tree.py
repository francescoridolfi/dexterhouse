# SPDX-License-Identifier: AGPL-3.0-or-later
"""Filesystem checks on a package directory: references, size, symlinks, binaries."""

import os
import stat
from pathlib import Path

from dexterhouse_schema.report import ValidationReport

MAX_PACKAGE_BYTES = 20 * 1024 * 1024
#: Binary files allowed in a package (images and glTF).
BINARY_SUFFIXES: frozenset[str] = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".glb", ".gltf", ".bin"}
)
_SKIP_DIRS = frozenset({".git"})
_SNIFF_BYTES = 8192


def resolve_ref(
    root: Path,
    value: str,
    report: ValidationReport,
    source: str,
    loc: str,
    max_bytes: int | None = None,
) -> Path | None:
    """Resolve a relative reference declared in `source`; it must be a file inside `root`.

    The value was already checked to be relative and free of `..` by the schema.
    """
    target = root / value
    if not target.resolve().is_relative_to(root.resolve()):
        report.error(source, f"{value!r} points outside the package", loc)
        return None
    if not target.is_file():
        report.error(source, f"referenced file {value!r} does not exist", loc)
        return None
    if max_bytes is not None and target.stat().st_size > max_bytes:
        report.error(source, f"{value!r} is larger than {max_bytes // 1024} KB", loc)
    return target


def _is_binary(path: Path) -> bool:
    with path.open("rb") as handle:
        return b"\0" in handle.read(_SNIFF_BYTES)


def check_tree(root: Path, report: ValidationReport, exempt: frozenset[str] = frozenset()) -> None:
    """Package size <= 20 MB, no symlinks, no executable or binary files (except `exempt`).

    `exempt` holds relative paths of package-local launchers (`tool.yaml` `command[0]`).
    """
    total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
        base = Path(dirpath)
        for name in sorted([*filenames, *(d for d in dirnames if (base / d).is_symlink())]):
            path = base / name
            rel = path.relative_to(root).as_posix()
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                report.error(rel, "symbolic links are not allowed")
                continue
            total += info.st_size
            if rel in exempt:
                continue
            if info.st_mode & 0o111:
                report.error(rel, "executable files are not allowed")
            if path.suffix.lower() not in BINARY_SUFFIXES and _is_binary(path):
                report.error(rel, "binary files are only allowed for images and glTF")
    if total > MAX_PACKAGE_BYTES:
        report.error(".", f"package is {total} bytes, limit {MAX_PACKAGE_BYTES}")
