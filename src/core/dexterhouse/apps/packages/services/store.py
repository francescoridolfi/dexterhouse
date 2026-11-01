# SPDX-License-Identifier: AGPL-3.0-or-later
"""Package files: fetch a git tag or a local folder into a staging dir, hash it, store it.

The registry hashes a version as `git archive --format=tar <ref> | sha256sum`
(infra/registry_ci.md, step 6): a git source is cloned shallow, archived with the same
command and the archive is what gets extracted, so the stored files are exactly the hashed
ones (no `.git`). Local and built-in folders get a tree hash instead (path + content of
every file, sorted), only used to tell whether a folder changed.
"""

import hashlib
import io
import shutil
import subprocess  # nosec B404: fixed argv, no shell, only `git clone` and `git archive`
import tarfile
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings

#: Same limit as the registry CI (package_schemas/README.md).
MAX_PACKAGE_BYTES = 20 * 1024 * 1024
GIT_TIMEOUT_S = 120
IGNORED = shutil.ignore_patterns(".git", "__pycache__", ".DS_Store", "*.pyc")
_IGNORED_NAMES = {".git", "__pycache__", ".DS_Store"}


class FetchError(Exception):
    """The source cannot be fetched (bad URL, missing tag, too big, git failure)."""


@dataclass(frozen=True)
class GitSource:
    url: str
    """Clone URL without the `git+` prefix and the `@ref` suffix."""
    ref: str

    @property
    def display(self) -> str:
        return f"git+{self.url}@{self.ref}"


def parse_git_source(source: str) -> GitSource:
    """`git+https://host/owner/repo@v1.2.0` (or `git+file://…@ref` when local sources are on)."""
    if not source.startswith("git+"):
        raise FetchError(f"not a git source: {source!r}")
    url, sep, ref = source[4:].rpartition("@")
    if not sep or not ref or "/" in ref:
        raise FetchError(f"git source needs a tag: {source!r} (git+https://…@v1.2.0)")
    parts = urlsplit(url)
    allowed = {"https", "file"} if settings.PACKAGES_ALLOW_LOCAL else {"https"}
    if parts.scheme not in allowed or (parts.scheme == "https" and not parts.hostname):
        raise FetchError(f"unsupported git URL {url!r}: only https:// repositories")
    if parts.username or parts.password:
        raise FetchError("credentials in the URL are not allowed")
    if ref.startswith("-") or any(c.isspace() for c in ref):
        raise FetchError(f"invalid ref {ref!r}")
    return GitSource(url, ref)


def staging_dir() -> Path:
    """A fresh directory under `PACKAGES_DIR/.staging` (same filesystem: moves are renames)."""
    base = Path(settings.PACKAGES_DIR) / ".staging"
    base.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=base))


def _git(*args: str, cwd: Path | None = None) -> bytes:
    git = shutil.which("git")
    if git is None:
        raise FetchError("git is not installed")
    env = {"GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1", "HOME": str(cwd or "/")}
    try:
        result = subprocess.run(  # noqa: S603  # nosec B603: argv list, URL and ref validated
            [git, "-c", "credential.helper=", "-c", "core.hooksPath=/dev/null", *args],
            cwd=cwd,
            env=env,
            capture_output=True,
            timeout=GIT_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise FetchError(f"git {args[0]} timed out after {GIT_TIMEOUT_S}s") from exc
    if result.returncode != 0:
        detail = result.stderr.decode(errors="replace").strip().splitlines()
        raise FetchError(f"git {args[0]} failed: {detail[-1] if detail else result.returncode}")
    return result.stdout


def fetch_git(source: GitSource, dest: Path) -> str:
    """Clone `source.ref` shallow, extract its `git archive` into `dest`; returns the sha256."""
    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        clone = Path(tmp) / "repo"
        _git(
            "clone", "--quiet", "--depth", "1", "--branch", source.ref, "--", source.url, str(clone)
        )
        archive = _git("archive", "--format=tar", source.ref, cwd=clone)
    if len(archive) > MAX_PACKAGE_BYTES:
        raise FetchError(f"package archive is {len(archive)} bytes, limit {MAX_PACKAGE_BYTES}")
    extract_tar(archive, dest)
    return hashlib.sha256(archive).hexdigest()


def extract_tar(data: bytes, dest: Path) -> None:
    """Extract a tar archive refusing links, devices and paths outside `dest`."""
    dest.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            members = tar.getmembers()
            if sum(m.size for m in members) > MAX_PACKAGE_BYTES:
                raise FetchError(f"package is larger than {MAX_PACKAGE_BYTES} bytes")
            for member in members:
                if not (member.isfile() or member.isdir()):
                    raise FetchError(f"unsupported entry in archive: {member.name}")
            tar.extractall(  # nosec B202: filter="data" rejects absolute paths and traversal
                dest,
                members=[m for m in members if m.isfile() or m.isdir()],
                filter="data",
            )
    except tarfile.TarError as exc:
        raise FetchError(f"invalid archive: {exc}") from exc


def copy_folder(src: Path, dest: Path) -> str:
    """Copy a local package folder (without `.git`, caches) into `dest`; returns its tree hash."""
    if not src.is_dir():
        raise FetchError(f"no package folder at {src}")
    size = sum(p.stat().st_size for p in _files(src))
    if size > MAX_PACKAGE_BYTES:
        raise FetchError(f"package is {size} bytes, limit {MAX_PACKAGE_BYTES}")
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, ignore=IGNORED, symlinks=True)
    return tree_hash(dest)


def _files(root: Path) -> list[Path]:
    return sorted(
        p
        for p in root.rglob("*")
        if (p.is_file() or p.is_symlink())
        and not _IGNORED_NAMES.intersection(p.relative_to(root).parts)
        and p.suffix != ".pyc"
    )


def tree_hash(root: Path) -> str:
    """sha256 over the sorted relative paths and contents of every file under `root`."""
    digest = hashlib.sha256()
    for path in _files(root):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest() if path.is_file() else b"link")
    return digest.hexdigest()


def install_path(organization_id: uuid.UUID | None, name: str, version: str) -> Path:
    """`PACKAGES_DIR/<global|organization id>/<name>/<version>`."""
    scope = str(organization_id) if organization_id else "global"
    return Path(settings.PACKAGES_DIR) / scope / name / version


def place(staged: Path, target: Path) -> None:
    """Move the staged files to their install path, replacing what is there."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    shutil.move(str(staged), str(target))


def discard(path: Path | str | None) -> None:
    """Remove a staging or install directory; never touches anything outside PACKAGES_DIR."""
    if not path:
        return
    target = Path(path).resolve()
    root = Path(settings.PACKAGES_DIR).resolve()
    if target != root and target.is_relative_to(root) and target.exists():
        shutil.rmtree(target, ignore_errors=True)
