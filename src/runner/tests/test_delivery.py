# SPDX-License-Identifier: AGPL-3.0-or-later
"""Delivery against local bare repositories: idempotency, no force, protected branches."""

import io
import json
import subprocess
import tarfile
import urllib.error
from pathlib import Path
from unittest import mock

import pytest

from dexterhouse_runner import delivery
from dexterhouse_runner.delivery import Delivery, _classify, open_pull_request, repo_path
from dexterhouse_runner.docker_manager import RunnerError


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def source(tmp_path: Path) -> Path:
    root = tmp_path / "work"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(
        root,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@x",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "a",
    )
    return root


def tar_of(root: Path):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        tar.add(root / ".git", arcname=".git")
    return iter([buffer.getvalue()])


def bare(tmp_path: Path, name: str = "remote.git") -> Path:
    remote = tmp_path / name
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    return remote


def test_pull_request_branch_is_pushed_once(source: Path, tmp_path: Path):
    remote = bare(tmp_path)
    commands: list[list[str]] = []

    def spy(argv, env, cwd):
        commands.append(argv)
        return delivery._run_git(argv, env, cwd)

    first = Delivery(tar_of(source), str(remote), None, run_git=spy).push(
        "pull_request", "dexterhouse/release-1", "main", {"title": "R1"}
    )
    assert not first.already
    assert _git(remote, "rev-parse", "dexterhouse/release-1").strip() == first.commit
    again = Delivery(tar_of(source), str(remote), None, run_git=spy).push(
        "pull_request", "dexterhouse/release-1", "main", None
    )
    assert again.already
    flat = [a for argv in commands for a in argv]
    assert "--force" not in flat
    assert not any(a.startswith("+") for a in flat)


def test_push_main_fast_forward_and_conflict(source: Path, tmp_path: Path):
    remote = bare(tmp_path)
    Delivery(tar_of(source), str(remote), None).push("push_main", None, "main", None)
    _git(
        source,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@x",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "b",
    )
    result = Delivery(tar_of(source), str(remote), None).push("push_main", None, "main", None)
    assert _git(remote, "rev-parse", "main").strip() == result.commit
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(remote), str(other)], check=True)
    _git(
        other,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@x",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "x",
    )
    _git(other, "push", "-q", "origin", "main")
    with pytest.raises(RunnerError) as exc:
        Delivery(tar_of(source), str(remote), None).push("push_main", None, "main", None)
    assert exc.value.code == "conflict"


def test_protected_main_is_reported(source: Path, tmp_path: Path):
    remote = bare(tmp_path)
    hook = remote / "hooks" / "pre-receive"
    hook.write_text(
        "#!/bin/sh\necho 'GH006: Protected branch update failed for refs/heads/main' >&2\nexit 1\n"
    )
    hook.chmod(0o755)
    with pytest.raises(RunnerError) as exc:
        Delivery(tar_of(source), str(remote), None).push("push_main", None, "main", None)
    assert exc.value.code == "protected_branch"


def test_token_reaches_git_only_through_askpass(source: Path, tmp_path: Path):
    remote = bare(tmp_path)
    seen: list[dict[str, str]] = []

    def spy(argv, env, cwd):
        seen.append({"argv": " ".join(argv), **env})
        return delivery._run_git(argv, env, cwd)

    Delivery(tar_of(source), str(remote), "s3cr3t-token", run_git=spy).push(
        "pull_request", "dexterhouse/release-2", "main", None
    )
    assert all("s3cr3t-token" not in s["argv"] for s in seen)
    assert all(s.get("DH_GIT_PASSWORD") == "s3cr3t-token" for s in seen)
    assert all(Path(s["GIT_ASKPASS"]).name == "askpass.sh" for s in seen)
    assert not Path(seen[0]["GIT_ASKPASS"]).exists()  # the temporary directory is gone
    config = (remote / "config").read_text()
    assert "s3cr3t" not in config


def test_unreachable_remote_is_network(source: Path, tmp_path: Path):
    with pytest.raises(RunnerError) as exc:
        Delivery(tar_of(source), str(tmp_path / "missing.git"), None).push(
            "push_main", None, "main", None
        )
    assert exc.value.code == "network"


def test_archive_without_repository(tmp_path: Path):
    empty = io.BytesIO()
    with tarfile.open(fileobj=empty, mode="w"):
        pass
    with pytest.raises(RunnerError):
        Delivery(iter([empty.getvalue()]), str(tmp_path), None).push(
            "push_main", None, "main", None
        )


@pytest.mark.parametrize(
    ("stderr", "code"),
    [
        ("remote: GH006: Protected branch update failed", "protected_branch"),
        ("fatal: Authentication failed for 'https://github.com/a/b'", "auth"),
        (" ! [rejected] main -> main (non-fast-forward)", "conflict"),
        ("fatal: unable to access: Could not resolve host: github.com", "network"),
        ("something odd", "network"),
    ],
)
def test_classify(stderr: str, code: str):
    assert _classify(stderr, "push").code == code
    assert _classify("odd", "rev-parse").code == "internal"


def test_repo_path():
    assert repo_path("https://github.com/acme/gymbook.git") == ("github.com", "acme/gymbook")
    assert repo_path("https://gitlab.example.com/g/sub/repo") == (
        "gitlab.example.com",
        "g/sub/repo",
    )
    assert repo_path("file:///tmp/x.git") is None
    assert repo_path("https://github.com/only") is None
    assert delivery._username("https://gitlab.com/a/b") == "oauth2"
    assert delivery._username("https://github.com/a/b") == "x-access-token"


class _Response:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return json.dumps(self.data).encode()


def test_github_pull_request():
    with mock.patch(
        "urllib.request.urlopen",
        return_value=_Response({"html_url": "https://github.com/a/b/pull/1"}),
    ) as call:
        url = open_pull_request(
            "https://github.com/a/b.git",
            "tok",
            "dexterhouse/release-1",
            "main",
            {"title": "Release 1", "body": "notes"},
        )
    assert url == "https://github.com/a/b/pull/1"
    request = call.call_args[0][0]
    assert request.full_url == "https://api.github.com/repos/a/b/pulls"
    assert request.headers["Authorization"] == "Bearer tok"
    assert json.loads(request.data)["head"] == "dexterhouse/release-1"


def test_github_existing_pull_request_and_missing_scope():
    error = urllib.error.HTTPError("u", 422, "exists", {}, None)
    with mock.patch(
        "urllib.request.urlopen", side_effect=[error, _Response([{"html_url": "https://x/pull/2"}])]
    ):
        assert (
            open_pull_request("https://github.com/a/b", "t", "h", "main", {"title": "t"})
            == "https://x/pull/2"
        )
    forbidden = urllib.error.HTTPError("u", 403, "scope", {}, None)
    with mock.patch("urllib.request.urlopen", side_effect=forbidden):
        assert open_pull_request("https://github.com/a/b", "t", "h", "main", {"title": "t"}) is None
    with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
        assert open_pull_request("https://github.com/a/b", "t", "h", "main", {"title": "t"}) is None
    assert open_pull_request("file:///x", "t", "h", "main", {"title": "t"}) is None


def test_gitlab_merge_request():
    with mock.patch(
        "urllib.request.urlopen",
        return_value=_Response({"web_url": "https://gitlab.com/g/r/-/merge_requests/3"}),
    ) as call:
        url = open_pull_request("https://gitlab.com/g/r.git", "tok", "h", "main", {"title": "t"})
    assert url.endswith("/merge_requests/3")
    request = call.call_args[0][0]
    assert request.full_url == "https://gitlab.com/api/v4/projects/g%2Fr/merge_requests"
    assert request.headers["Private-token"] == "tok"
