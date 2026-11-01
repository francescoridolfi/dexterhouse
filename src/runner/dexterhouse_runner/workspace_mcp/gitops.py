# SPDX-License-Identifier: AGPL-3.0-or-later
"""`git.*` tools of the agents (contracts/tools/git.md); push, merge and branches are system.

`git.commit` refuses `main`, messages that are not Conventional Commits and any staged file
in which detect-secrets finds a secret (`secrets_blocked`, nothing is committed). The author
is `<display name> (DexterHouse) <agents@dexterhouse.dev>`, set by the runner per call; the
committer is DexterHouse; no attribution trailer is ever added (CD-009).
"""

import json
import os
import re
import subprocess  # nosec B404 - git and detect-secrets on the workspace
from typing import Any

from dexterhouse_runner.workspace_mcp.base import (
    FULL_OUTPUT_LIMIT,
    Config,
    ToolFailure,
    clip,
    resolve,
)

PROTECTED = frozenset({"main", "master"})
AUTHOR_EMAIL = "agents@dexterhouse.dev"
COMMITTER = ("DexterHouse", "noreply@dexterhouse.dev")
CONVENTIONAL = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([\w./-]+\))?!?: \S.*"
)
_TRAILER = re.compile(r"^(co-authored-by|signed-off-by):", re.IGNORECASE | re.MULTILINE)
GIT_TIMEOUT_S = 60


def git(cfg: Config, *args: str, check: bool = True, timeout: int = GIT_TIMEOUT_S) -> str:
    env = {
        **{k: v for k, v in os.environ.items() if not k.startswith("DH_")},
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_COMMITTER_NAME": COMMITTER[0],
        "GIT_COMMITTER_EMAIL": COMMITTER[1],
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    try:
        done = subprocess.run(  # noqa: S603  # nosec B603 B607 - fixed git argv, no shell
            ["git", "-C", str(cfg.root), *args],  # noqa: S607
            capture_output=True,
            env=env,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolFailure("timeout", f"git {args[0]} timed out") from exc
    out = done.stdout.decode("utf-8", errors="replace")
    if check and done.returncode != 0:
        err = done.stderr.decode("utf-8", errors="replace").strip()
        raise ToolFailure("invalid", f"git {args[0]} failed: {err[-1500:]}")
    return out


def current_branch(cfg: Config) -> str:
    return git(cfg, "rev-parse", "--abbrev-ref", "HEAD").strip()


def status(cfg: Config) -> dict:
    lines = git(cfg, "status", "--porcelain=v1", "-uall").splitlines()
    files = [{"status": line[:2].strip() or "?", "path": line[3:]} for line in lines if line]
    return {"branch": current_branch(cfg), "files": files, "clean": not files}


def diff(
    cfg: Config,
    base: str = "main",
    head: str = "HEAD",
    path: str | None = None,
    stat_only: bool = False,
) -> dict:
    args = ["diff", "--stat" if stat_only else "--patch", f"{base}...{head}"]
    if head == "WORKTREE":
        args = ["diff", "--stat" if stat_only else "--patch", base]
    if path:
        resolve(cfg.root, path)
        args += ["--", path]
    text = git(cfg, *args)
    inline, cut = clip(text)
    result: dict[str, Any] = {"diff": inline, "truncated": cut}
    if cut:
        result["full_output"] = text[:FULL_OUTPUT_LIMIT]
    return result


def log(cfg: Config, max: int = 20, path: str | None = None, ref: str = "HEAD") -> dict:
    fmt = "%H%x1f%an <%ae>%x1f%aI%x1f%s"
    args = ["log", f"--max-count={min(max, 500)}", f"--format={fmt}", ref]
    if path:
        resolve(cfg.root, path)
        args += ["--", path]
    commits = []
    for line in git(cfg, *args).splitlines():
        sha, author, date, subject = [*line.split("\x1f"), "", "", ""][:4]
        commits.append({"commit": sha, "author": author, "date": date, "message": subject})
    return {"commits": commits}


def show(cfg: Config, ref: str, path: str | None = None) -> dict:
    if ref.startswith("-"):
        raise ToolFailure("invalid", "ref must not start with '-'")
    if path:
        resolve(cfg.root, path)
        text = git(cfg, "show", f"{ref}:{path}")
    else:
        text = git(cfg, "show", "--stat", "--patch", ref)
    inline, cut = clip(text)
    result: dict[str, Any] = {"content": inline, "truncated": cut}
    if cut:
        result["full_output"] = text[:FULL_OUTPUT_LIMIT]
    return result


def add(cfg: Config, paths: list[str]) -> dict:
    if not paths:
        raise ToolFailure("invalid", "paths is required")
    for path in paths:
        resolve(cfg.root, path, write=True)
    git(cfg, "add", "--", *paths)
    return {"staged": staged(cfg)}


def staged(cfg: Config) -> list[str]:
    out = git(cfg, "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR")
    return [p for p in out.split("\x00") if p]


def scan_secrets(cfg: Config, files: list[str]) -> dict[str, int]:
    """detect-secrets on the staged files: {file: findings}."""
    present = [f for f in files if (cfg.root / f).is_file()]
    if not present:
        return {}
    try:
        done = subprocess.run(  # noqa: S603  # nosec B603 B607 - fixed argv, no shell
            ["detect-secrets", "scan", "--all-files", *present],  # noqa: S607
            cwd=cfg.root,
            capture_output=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ToolFailure("internal", f"detect-secrets did not run: {exc}") from exc
    if done.returncode != 0:
        raise ToolFailure("internal", f"detect-secrets failed: {done.stderr.decode()[-500:]}")
    results = json.loads(done.stdout or b"{}").get("results", {})
    return {name: len(found) for name, found in results.items() if found}


def _lint(cfg: Config) -> dict[str, Any] | None:
    """`stack.lint_command`, reported to the agent but never blocking."""
    if not cfg.lint_command:
        return None
    from dexterhouse_runner.workspace_mcp import shell

    try:
        result = shell.run(cfg, cfg.lint_command, timeout_s=120, check_quota=False)
    except ToolFailure as exc:
        result = {**exc.data, "error": exc.detail}
    output, _ = clip(f"{result.get('stdout', '')}{result.get('stderr', '')}", 8 * 1024)
    return {"command": cfg.lint_command, "exit_code": result.get("exit_code"), "output": output}


def commit(cfg: Config, message: str, all: bool = False, author: str = "Agent") -> dict:
    branch = current_branch(cfg)
    if branch in PROTECTED:
        raise ToolFailure(
            "protected_branch", f"commits on {branch} are refused: work on the task branch"
        )
    message = (message or "").strip()
    if not CONVENTIONAL.match(message.splitlines()[0] if message else ""):
        raise ToolFailure(
            "args_policy", "the message must be a Conventional Commit: `type(scope): subject`"
        )
    if _TRAILER.search(message):
        raise ToolFailure("args_policy", "attribution trailers are not allowed (CD-009)")
    if all:
        git(cfg, "add", "--all")
    files = staged(cfg)
    deleted = [
        p
        for p in git(cfg, "diff", "--cached", "--name-only", "-z", "--diff-filter=D").split("\x00")
        if p
    ]
    if not files and not deleted:
        raise ToolFailure("invalid", "nothing staged to commit")
    findings = scan_secrets(cfg, files)
    if findings:
        raise ToolFailure(
            "secrets_blocked",
            "detect-secrets found possible secrets; remove them (use environment variables) "
            "and commit again: " + ", ".join(sorted(findings)),
            files=sorted(findings),
            count=sum(findings.values()),
        )
    lint = _lint(cfg)
    name = re.sub(r"[<>\n]", "", author).strip() or "Agent"
    git(
        cfg,
        "-c",
        "core.hooksPath=/dev/null",
        "commit",
        "--quiet",
        "--no-verify",
        f"--author={name} (DexterHouse) <{AUTHOR_EMAIL}>",
        "-m",
        message,
    )
    sha = git(cfg, "rev-parse", "HEAD").strip()
    result: dict[str, Any] = {
        "commit": sha,
        "branch": branch,
        "files_changed": len(files) + len(deleted),
        "message": message.splitlines()[0],
    }
    if lint is not None:
        result["lint"] = lint
    return result


def checkout_file(cfg: Config, path: str, ref: str = "HEAD") -> dict:
    resolve(cfg.root, path, write=True)
    if ref.startswith("-"):
        raise ToolFailure("invalid", "ref must not start with '-'")
    git(cfg, "checkout", ref, "--", path)
    return {"path": path, "ref": ref}


def stash(cfg: Config) -> dict:
    out = git(cfg, "stash", "push", "--include-untracked", "-m", "dexterhouse")
    return {"stashed": "No local changes" not in out}


def stash_pop(cfg: Config) -> dict:
    git(cfg, "stash", "pop")
    return {"restored": True}
