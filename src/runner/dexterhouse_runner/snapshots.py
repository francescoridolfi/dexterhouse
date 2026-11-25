# SPDX-License-Identifier: AGPL-3.0-or-later
"""Project snapshots and workspace restore for change requests (ADR-0018).

`snapshot`: the workspace's `.git` is copied out (as for delivery) and git runs here, in a
private temporary directory: `git bundle create --all` into `RUNNER_SNAPSHOT_DIR`, written to a
temporary name and renamed over `<project_id>.bundle`. The copied `.git` is the agent's to
write, so its config, hooks and alternates are dropped before git reads it.

`restore`: the repository of a new workspace is built here too, from the bundle (every branch
and tag) or from one `branch` of the remote (as local `main`), with the token of a grant
reaching git only through `GIT_ASKPASS` as in `delivery.py`; the tree is then copied into the
workspace volume (uid 1000). The token is never in a URL, a config file or the workspace.
"""

import os
import shutil
import stat
import subprocess  # nosec B404 - git with a fixed argv, through delivery._run_git
import tarfile
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dexterhouse_runner.delivery import _ASKPASS, _classify, _run_git, _username, extract_git_dir
from dexterhouse_runner.docker_manager import RunnerError

UID = 1000
_SAFE_CONFIG = "[core]\n\trepositoryformatversion = 0\n\tbare = true\n"


@dataclass
class Restored:
    commit: str
    tar: Path


def bundle_path(directory: str | Path, project_id: uuid.UUID) -> Path:
    return Path(directory) / f"{uuid.UUID(str(project_id))}.bundle"


class Git:
    """git in a private directory of the runner, with a token only through `GIT_ASKPASS`."""

    def __init__(
        self,
        root: Path,
        token: str | None = None,
        remote_url: str = "",
        run_git: Callable[..., Any] | None = None,
    ) -> None:
        self.root = root
        self.run_git = run_git or _run_git
        askpass = root / "askpass.sh"
        askpass.write_text(_ASKPASS, encoding="utf-8")
        askpass.chmod(stat.S_IRWXU)
        self.env = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": str(root),
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_ASKPASS": str(askpass),
        }
        if token:
            self.env["DH_GIT_USERNAME"] = _username(remote_url)
            self.env["DH_GIT_PASSWORD"] = token

    def __call__(self, git_dir: Path, *args: str, work_tree: Path | None = None) -> str:
        argv = [
            "git",
            "-c",
            "credential.helper=",
            "-c",
            "core.askPass=" + self.env["GIT_ASKPASS"],
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "protocol.ext.allow=never",
            f"--git-dir={git_dir}",
        ]
        if work_tree is not None:
            argv.append(f"--work-tree={work_tree}")
        try:
            done = self.run_git([*argv, *args], self.env, self.root)
        except subprocess.TimeoutExpired:
            raise RunnerError("timeout", f"git {args[0]} timed out") from None
        if done.returncode != 0:
            err = done.stderr.decode("utf-8", errors="replace")
            raise _classify(err, args[0])
        return done.stdout.decode("utf-8", errors="replace")


def _sanitize(git_dir: Path) -> None:
    """Keep only refs and objects of a copied `.git` (its config and hooks are untrusted)."""
    shutil.rmtree(git_dir / "hooks", ignore_errors=True)
    for name in ("objects/info/alternates", "commondir", "gitdir", "info/attributes"):
        (git_dir / name).unlink(missing_ok=True)
    (git_dir / "config").write_text(_SAFE_CONFIG, encoding="utf-8")


def write_bundle(
    git_dir_tar: Any,
    directory: str | Path,
    project_id: uuid.UUID,
    run_git: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """`git bundle create <directory>/<project_id>.bundle --all`, atomically -> {commit, size}."""
    target = bundle_path(directory, project_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    with tempfile.TemporaryDirectory(prefix="dh-snapshot-") as tmp:
        root = Path(tmp)
        repo = extract_git_dir(git_dir_tar, root)
        _sanitize(repo)
        git = Git(root, run_git=run_git)
        try:
            commit = git(repo, "rev-parse", "--verify", "refs/heads/main^{commit}").strip()
        except RunnerError:
            commit = git(repo, "rev-parse", "--verify", "HEAD^{commit}").strip()
        try:
            git(repo, "bundle", "create", str(partial), "--all")
            os.replace(partial, target)
        finally:
            partial.unlink(missing_ok=True)
    return {"commit": commit, "size": target.stat().st_size}


def drop_bundle(directory: str | Path, project_id: uuid.UUID) -> bool:
    target = bundle_path(directory, project_id)
    try:
        target.unlink()
    except FileNotFoundError:
        return False
    return True


def build_repository(
    root: Path,
    source: str,
    *,
    bundle: Path | None = None,
    remote_url: str | None = None,
    branch: str = "main",
    token: str | None = None,
    run_git: Callable[..., Any] | None = None,
) -> Restored:
    """A working tree on `main` under `root`, as a tar for the workspace volume."""
    if source == "snapshot":
        if bundle is None or not bundle.is_file():
            raise RunnerError("not_found", "the project has no snapshot")
        url = str(bundle)
        refspecs = ["+refs/heads/*:refs/heads/*", "+refs/tags/*:refs/tags/*"]
    else:
        if not remote_url or remote_url.startswith("-"):
            raise RunnerError("invalid", "restore from the remote needs a remote_url")
        url = remote_url
        refspecs = [f"+refs/heads/{branch}:refs/heads/main"]
    tree = root / "tree"
    tree.mkdir()
    repo = tree / ".git"
    git = Git(root, token, remote_url or "", run_git)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "fetch", "--quiet", "--no-tags", "--update-head-ok", url, *refspecs)
    try:
        git(repo, "rev-parse", "--verify", "refs/heads/main^{commit}")
    except RunnerError:
        raise RunnerError("not_found", f"the {source} has no branch main") from None
    git(repo, "reset", "-q", "--hard", "main", work_tree=tree)
    commit = git(repo, "rev-parse", "HEAD").strip()
    (repo / "FETCH_HEAD").unlink(missing_ok=True)
    archive = root / "restore.tar"
    with tarfile.open(archive, "w") as tar:
        for child in sorted(tree.iterdir()):
            tar.add(child, arcname=child.name, filter=_owned)
    return Restored(commit, archive)


def _owned(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = info.gid = UID
    info.uname = info.gname = ""
    return info
