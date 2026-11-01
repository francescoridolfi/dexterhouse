# SPDX-License-Identifier: AGPL-3.0-or-later
"""Package folders, a registry index on disk and a fake git fetcher for installer tests."""

import io
import json
import shutil
import subprocess
import tarfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from dexterhouse.apps.packages.services import index as registry
from dexterhouse.apps.packages.services import installer, store

AGENT = {
    "schema": 1,
    "role": "security_reviewer",
    "display_name": "Security Reviewer",
    "model_profile": "strong",
    "tools": ["memory.search"],
    "skills": [],
    "prompts": {"system": "prompts/system.md"},
    "output_contract": {"artifacts": ["review"], "schema": "review"},
}
TOOL = {
    "schema": 1,
    "name": "git-tools",
    "transport": "stdio",
    "runs_in": "runner",
    "command": ["uvx", "mcp-server-git@0.6.2"],
    "permissions": [
        {"id": "git.diff", "mcp_tool": "git_diff", "description": "Read a diff", "risk": "low"},
        {"id": "git.push", "mcp_tool": "git_push", "description": "Push", "risk": "high"},
    ],
    "network": "none",
}


def manifest(name: str, kind: str, version: str = "1.0.0", **extra: Any) -> dict[str, Any]:
    return {
        "schema": 1,
        "kind": kind,
        "name": name,
        "version": version,
        "description": f"{name} for tests",
        "author": {"name": "Jane", "github": "janedoe"},
        "license": "MIT",
        "compat": {"core": ">=0.1,<2.0"},
        **extra,
    }


def write_package(
    root: Path,
    name: str = "security-reviewer",
    kind: str = "agent",
    version: str = "1.0.0",
    definition: dict[str, Any] | None = None,
    **extra: Any,
) -> Path:
    """A valid package folder (agent by default) at `root`."""
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    (root / "dexterhouse.yaml").write_text(yaml.safe_dump(manifest(name, kind, version, **extra)))
    (root / "README.md").write_text(f"# {name}\n")
    if kind == "agent":
        (root / "prompts").mkdir()
        (root / "prompts" / "system.md").write_text("# Role\nReview security.\n")
        (root / "agent.yaml").write_text(yaml.safe_dump(definition or AGENT))
    elif kind == "tool":
        (root / "tool.yaml").write_text(yaml.safe_dump(definition or {**TOOL, "name": name}))
    else:
        process = definition or {
            "schema": 1,
            "name": name,
            "version": version,
            "phases": [{"id": "review", "agent": "reviewer", "produces": ["review"]}],
        }
        (root / "process.yaml").write_text(yaml.safe_dump(process))
    return root


@pytest.fixture
def pkg_dir(tmp_path: Path) -> Callable[..., Path]:
    def make(name: str = "security-reviewer", kind: str = "agent", **kwargs: Any) -> Path:
        return write_package(
            tmp_path / "src" / f"{name}-{kwargs.get('version', '1.0.0')}", name, kind, **kwargs
        )

    return make


@pytest.fixture(autouse=True)
def _private_store(settings, tmp_path: Path) -> None:
    settings.PACKAGES_DIR = tmp_path / "store"
    settings.REGISTRY_INDEX_URL = ""
    registry.clear_cache()


def tar_bytes(root: Path) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for path in sorted(root.rglob("*")):
            tar.add(path, arcname=path.relative_to(root).as_posix(), recursive=False)
    return buffer.getvalue()


@pytest.fixture
def fake_git(monkeypatch) -> dict[str, Path]:
    """`fetch_git` without git: `repos[url]` is a folder, the sha is the tar of its files."""
    import hashlib

    repos: dict[str, Path] = {}

    def fetch(source: store.GitSource, dest: Path) -> str:
        if source.url not in repos:
            raise store.FetchError(f"git clone failed: repository {source.url} not found")
        data = tar_bytes(repos[source.url])
        store.extract_tar(data, dest)
        return hashlib.sha256(data).hexdigest()

    monkeypatch.setattr(store, "fetch_git", fetch)
    return repos


def sha_of(root: Path) -> str:
    import hashlib

    return hashlib.sha256(tar_bytes(root)).hexdigest()


@pytest.fixture
def index_file(settings, tmp_path: Path) -> Callable[..., Path]:
    """Write `index.json` and point REGISTRY_INDEX_URL at it."""

    def write(*entries: dict[str, Any]) -> Path:
        path = tmp_path / "registry" / "index.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "generated_at": "2026-11-01T10:00:00Z",
                    "core_latest": "0.1.0",
                    "packages": list(entries),
                }
            )
        )
        settings.REGISTRY_INDEX_URL = path.as_uri()
        registry.clear_cache()
        return path

    return write


def index_entry(
    name: str, repo: str, versions: list[tuple[str, str, str]], kind: str = "agent", **extra: Any
) -> dict[str, Any]:
    """`versions` = [(version, ref, sha256)]."""
    return {
        "name": name,
        "kind": kind,
        "description": name,
        "tags": [],
        "author_github": "janedoe",
        "verified": False,
        "latest": versions[-1][0],
        "versions": [
            {"version": v, "ref": r, "sha256": s, "compat_core": ">=0.1,<2.0"}
            for v, r, s in versions
        ],
        "repo": repo,
        "risk": "low",
        **extra,
    }


def git_repo(path: Path, source: Path, tag: str) -> Path:
    """A bare repository at `path` holding `source` at `tag` (real git, slow tests)."""
    work = path.with_suffix(".work")
    shutil.copytree(source, work)
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@x",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@x",
        "HOME": str(path.parent),
    }
    commands = [
        ["init", "-q", "-b", "main"],
        ["add", "-A"],
        ["commit", "-qm", "v"],
        ["tag", tag],
    ]
    for args in commands:
        subprocess.run(["git", *args], cwd=work, env=env, check=True)  # noqa: S603, S607
    clone = ["git", "clone", "-q", "--bare", str(work), str(path)]
    subprocess.run(clone, env=env, check=True)  # noqa: S603
    return path


def run(source: str, **kwargs: Any):  # type: ignore[no-untyped-def]
    return installer.install(source=source, **{"organization": None, **kwargs})
