# SPDX-License-Identifier: AGPL-3.0-or-later
"""`runner.system.ls_tree` / `read_file`: read-only git plumbing for the UI's Code app."""

import subprocess
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from dexterhouse_schema.runner import LsTree, ReadFile


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def code(runner: SimpleNamespace, workspace: uuid.UUID) -> Path:
    root = runner.docker.root(workspace)
    (root / "src").mkdir(exist_ok=True)
    (root / "src" / "app.py").write_text("def main():\n    return 1\n")
    (root / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00")
    (root / "big.txt").write_text("x" * 5000)
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=T", "-c", "user.email=t@e.invalid", "commit", "-qm", "feat: app")
    return root


def test_ls_tree_lists_files_at_a_commit(runner, workspace, code):
    first = _git(code, "rev-parse", "HEAD").strip()
    (code / "later.py").write_text("x = 1\n")  # not committed: not in the tree
    result = runner.service.ls_tree(LsTree(workspace_id=workspace))
    assert result.ok, result
    data = result.data
    assert data["commit"] == first
    assert data["branch"] == "main"
    paths = {e["path"]: e for e in data["entries"]}
    assert paths["src/app.py"]["size"] == len("def main():\n    return 1\n")
    assert "later.py" not in paths
    assert data["truncated"] is False
    short = runner.service.ls_tree(LsTree(workspace_id=workspace, max_entries=1))
    assert len(short.data["entries"]) == 1
    assert short.data["truncated"] is True
    assert _git(code, "status", "--porcelain").strip() == "?? later.py"  # tree untouched


def test_read_file_text_binary_large_and_missing(runner, workspace, code):
    text = runner.service.read_file(ReadFile(workspace_id=workspace, path="src/app.py"))
    assert text.ok
    assert text.data["content"].startswith("def main")
    assert text.data["binary"] is False
    png = runner.service.read_file(ReadFile(workspace_id=workspace, path="logo.png"))
    assert png.data["binary"] is True
    assert png.data["content"] is None
    big = runner.service.read_file(ReadFile(workspace_id=workspace, path="big.txt", max_bytes=100))
    assert big.data["too_large"] is True
    assert big.data["content"] is None
    missing = runner.service.read_file(ReadFile(workspace_id=workspace, path="nope.py"))
    assert missing.error.code == "not_found"
    folder = runner.service.read_file(ReadFile(workspace_id=workspace, path="src"))
    assert folder.error.code == "invalid"
    bad_ref = runner.service.ls_tree(LsTree(workspace_id=workspace, ref="nope"))
    assert bad_ref.error.code == "not_found"


@pytest.mark.parametrize("path", ["../etc/passwd", "/etc/passwd", "a/./b", "a//b", "x\ny"])
def test_paths_outside_the_repository_are_refused(path):
    with pytest.raises(ValidationError):
        ReadFile(workspace_id=uuid.uuid4(), path=path)


@pytest.mark.parametrize("ref", ["-x", "main..evil", "--output=/tmp/x"])
def test_refs_are_never_options_or_ranges(ref):
    with pytest.raises(ValidationError):
        LsTree(workspace_id=uuid.uuid4(), ref=ref)
