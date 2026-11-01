# SPDX-License-Identifier: AGPL-3.0-or-later
"""`runner.system.deliver`: push the release and open the pull request (CD-039, ADR-0016).

The repository is copied out of the workspace (`docker cp` of `.git`) into a private
temporary directory of the runner, and git runs here, never in the workspace: the token,
redeemed once from a grant, lives in this process's memory and reaches git only through a
temporary `GIT_ASKPASS` script reading it from the child's environment; it is never in a
URL, a config file or the workspace. Never `--force`: a rejected push is `conflict` or
`protected_branch`. The remote state is checked first, so a retried delivery is a no-op.
"""

import json
import os
import re
import stat
import subprocess  # nosec B404 - git with a fixed argv
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from dexterhouse_runner.docker_manager import RunnerError

logger = structlog.get_logger(__name__)

GIT_TIMEOUT_S = 120
API_TIMEOUT_S = 20
_ASKPASS = """#!/bin/sh
case "$1" in
  Username*) printf '%s\\n' "$DH_GIT_USERNAME" ;;
  *) printf '%s\\n' "$DH_GIT_PASSWORD" ;;
esac
"""
_PROTECTED = re.compile(
    r"protected branch|GH006|pre-receive hook declined|not allowed to push", re.I
)
_AUTH = re.compile(
    r"authentication failed|could not read username|403|401|permission denied|"
    r"invalid username or password",
    re.I,
)
_NETWORK = re.compile(
    r"could not resolve host|unable to access|connection (refused|timed out)|"
    r"timed out|network is unreachable|does not appear to be a git repository",
    re.I,
)
_REJECTED = re.compile(r"non-fast-forward|\[rejected\]|fetch first|failed to push", re.I)


@dataclass
class Delivered:
    commit: str
    branch: str
    pr_url: str | None = None
    already: bool = False


#: Every git argv run by a delivery goes through here (ST-15 spies on it: never `--force`).
def _run_git(argv: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603  # nosec B603 - fixed argv, no shell
        argv, cwd=cwd, env=env, capture_output=True, timeout=GIT_TIMEOUT_S, check=False
    )


class Delivery:
    def __init__(
        self,
        git_dir_tar: Any,
        remote_url: str,
        token: str | None,
        run_git: Callable[..., subprocess.CompletedProcess] | None = None,
    ) -> None:
        self.tar = git_dir_tar
        self.remote_url = remote_url
        self.token = token
        self.run_git = run_git or _run_git

    # git ----------------------------------------------------------------------------------

    def _env(self, askpass: Path) -> dict[str, str]:
        env = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": str(askpass.parent),
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_ASKPASS": str(askpass),
        }
        if self.token:
            env["DH_GIT_USERNAME"] = _username(self.remote_url)
            env["DH_GIT_PASSWORD"] = self.token
        return env

    def git(self, repo: Path, env: dict[str, str], *args: str, check: bool = True) -> str:
        argv = [
            "git",
            "-c",
            "credential.helper=",
            "-c",
            "core.askPass=" + env["GIT_ASKPASS"],
            f"--git-dir={repo}",
            *args,
        ]
        if "--force" in argv or any(a.startswith("+") for a in args):
            raise RunnerError("internal", "deliver never force-pushes")  # pragma: no cover
        done = self.run_git(argv, env, repo.parent)
        err = done.stderr.decode("utf-8", errors="replace")
        if check and done.returncode != 0:
            raise _classify(err, args[0])
        return done.stdout.decode("utf-8", errors="replace")

    def remote_head(self, repo: Path, env: dict[str, str], branch: str) -> str | None:
        out = self.git(repo, env, "ls-remote", self.remote_url, f"refs/heads/{branch}")
        line = out.strip().splitlines()
        return line[0].split()[0] if line else None

    def is_ancestor(self, repo: Path, env: dict[str, str], ancestor: str, head: str) -> bool:
        try:
            self.git(repo, env, "cat-file", "-e", f"{ancestor}^{{commit}}")
        except RunnerError:
            return False
        done = self.run_git(
            ["git", f"--git-dir={repo}", "merge-base", "--is-ancestor", ancestor, head],
            env,
            repo.parent,
        )
        return done.returncode == 0

    def push(
        self, mode: str, branch: str | None, base: str, pr: dict[str, str] | None
    ) -> Delivered:
        with tempfile.TemporaryDirectory(prefix="dh-deliver-") as tmp:
            root = Path(tmp)
            askpass = root / "askpass.sh"
            askpass.write_text(_ASKPASS, encoding="utf-8")
            askpass.chmod(stat.S_IRWXU)
            env = self._env(askpass)
            repo = self._extract(root)
            head = self.git(repo, env, "rev-parse", f"refs/heads/{base}").strip()
            target = base if mode == "push_main" else (branch or "dexterhouse/release-1")
            remote = self.remote_head(repo, env, target)
            if remote == head:
                logger.info("runner.deliver_already_done", branch=target, commit=head)
                result = Delivered(head, target, already=True)
            else:
                if remote is not None:
                    self.git(
                        repo,
                        env,
                        "fetch",
                        "--quiet",
                        self.remote_url,
                        f"refs/heads/{target}:refs/dh-remote/{target}",
                        check=False,
                    )
                    if not self.is_ancestor(repo, env, remote, head):
                        raise RunnerError(
                            "conflict", f"{target} on the remote has commits the release lacks"
                        )
                self.git(
                    repo,
                    env,
                    "push",
                    "--porcelain",
                    self.remote_url,
                    f"refs/heads/{base}:refs/heads/{target}",
                )
                result = Delivered(head, target)
            if mode == "pull_request" and pr is not None and self.token:
                result.pr_url = open_pull_request(self.remote_url, self.token, target, base, pr)
            return result

    def _extract(self, root: Path) -> Path:
        """Unpack the workspace's `.git` (a `get_archive` tar stream) under `root`."""
        archive = root / "git.tar"
        with archive.open("wb") as out:
            for chunk in self.tar:
                out.write(chunk)
        with tarfile.open(archive) as tar:
            tar.extractall(root, filter="data")
        archive.unlink()
        repo = root / ".git"
        if not repo.is_dir():
            raise RunnerError("internal", "the workspace has no git repository")
        return repo


def _username(remote_url: str) -> str:
    host = urllib.parse.urlsplit(remote_url).hostname or ""
    if "gitlab" in host:
        return "oauth2"
    return "x-access-token"


def _classify(stderr: str, command: str) -> RunnerError:
    text = stderr.strip()[-1500:]
    if _PROTECTED.search(text):
        return RunnerError("protected_branch", text)
    if _AUTH.search(text):
        return RunnerError("auth", text)
    if _REJECTED.search(text):
        return RunnerError("conflict", text)
    if _NETWORK.search(text):
        return RunnerError("network", text)
    return RunnerError("network" if command in ("push", "ls-remote", "fetch") else "internal", text)


# Pull requests ------------------------------------------------------------------------------


def repo_path(remote_url: str) -> tuple[str, str] | None:
    """(host, owner/name) of an https remote, without `.git`."""
    parts = urllib.parse.urlsplit(remote_url)
    if parts.scheme != "https" or not parts.hostname:
        return None
    path = parts.path.strip("/").removesuffix(".git")
    return (parts.hostname, path) if path.count("/") >= 1 else None


def _request(url: str, token: str, body: dict[str, Any] | None, *, gitlab: bool) -> Any:
    if not url.startswith("https://"):
        raise RunnerError("network", "pull request APIs are reached over https only")
    headers = {"Accept": "application/json", "User-Agent": "dexterhouse-runner"}
    if gitlab:
        headers["PRIVATE-TOKEN"] = token
    else:
        headers["Authorization"] = f"Bearer {token}"
        headers["Accept"] = "application/vnd.github+json"
    data = json.dumps(body).encode() if body is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(  # noqa: S310 - https checked above
        url, data=data, headers=headers, method="POST" if data else "GET"
    )
    with urllib.request.urlopen(request, timeout=API_TIMEOUT_S) as response:  # noqa: S310  # nosec B310 - https checked above
        return json.loads(response.read() or b"null")


def open_pull_request(
    remote_url: str, token: str, head: str, base: str, pr: dict[str, str]
) -> str | None:
    """Open (or find) the PR/MR; None when the host or the token scope does not allow it."""
    located = repo_path(remote_url)
    if located is None:
        return None
    host, path = located
    gitlab = "gitlab" in host
    try:
        if gitlab:
            api = (
                f"https://{host}/api/v4/projects/{urllib.parse.quote(path, safe='')}/merge_requests"
            )
            body = {
                "source_branch": head,
                "target_branch": base,
                "title": pr["title"],
                "description": pr.get("body", ""),
            }
            return _request(api, token, body, gitlab=True).get("web_url")
        api = (
            f"https://api.{host}/repos/{path}/pulls"
            if host == "github.com"
            else (f"https://{host}/api/v3/repos/{path}/pulls")
        )
        body = {"title": pr["title"], "body": pr.get("body", ""), "head": head, "base": base}
        return _request(api, token, body, gitlab=False).get("html_url")
    except urllib.error.HTTPError as exc:
        if exc.code == 422 and not gitlab:  # already open: find it
            owner = path.split("/")[0]
            query = urllib.parse.urlencode({"head": f"{owner}:{head}", "state": "open"})
            try:
                found = _request(f"{api}?{query}", token, None, gitlab=False)
                return found[0]["html_url"] if found else None
            except (urllib.error.URLError, KeyError, IndexError, TypeError):
                return None
        logger.warning("runner.pull_request_not_opened", status=exc.code, host=host)
        return None
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        logger.warning("runner.pull_request_not_opened", error=str(exc), host=host)
        return None
