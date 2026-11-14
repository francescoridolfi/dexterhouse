# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only views of a workspace repository for the UI (`ls_tree`, `read_file`).

Plain git plumbing on an object id: no checkout, no working tree change, no MCP session and
no agent turn, so a reader never disturbs the agents. `ref` and `path` are already checked
by the schema (`Ref`, `RepoPath`): never an option, a range or a path outside the repo.
"""

from collections.abc import Callable
from typing import Any

from dexterhouse_runner.docker_manager import RunnerError

Exec = Callable[[list[str]], tuple[int, str, str]]

#: Bytes looked at to tell a binary from text.
SNIFF = 8000


def resolve(run: Exec, ref: str) -> str:
    code, out, _ = run(["git", "rev-parse", "--verify", "-q", f"{ref}^{{commit}}"])
    if code != 0 or not out.strip():
        raise RunnerError("not_found", f"unknown ref {ref}")
    return out.strip()


def current_branch(run: Exec) -> str | None:
    code, out, _ = run(["git", "symbolic-ref", "-q", "--short", "HEAD"])
    return (out.strip() or None) if code == 0 else None


def ls_tree(run: Exec, ref: str, max_entries: int) -> dict[str, Any]:
    commit = resolve(run, ref)
    code, out, err = run(["git", "ls-tree", "-r", "-l", "-z", "--full-tree", commit])
    if code != 0:
        raise RunnerError("internal", f"git ls-tree: {err.strip()[-500:]}")
    entries: list[dict[str, Any]] = []
    records = [r for r in out.split("\0") if r]
    for record in records[:max_entries]:
        meta, _, path = record.partition("\t")
        fields = meta.split()
        if len(fields) < 4 or not path:
            continue
        kind = fields[1]
        entries.append(
            {
                "path": path,
                "type": "submodule" if kind == "commit" else "file",
                "size": int(fields[3]) if fields[3].isdigit() else None,
            }
        )
    return {
        "ref": ref,
        "commit": commit,
        "branch": current_branch(run),
        "entries": entries,
        "truncated": len(records) > max_entries,
    }


def looks_binary(text: str) -> bool:
    """NUL bytes, or bytes that are not UTF-8 (decoded as U+FFFD by the exec)."""
    head = text[:SNIFF]
    return "\0" in head or "�" in text


def read_file(run: Exec, ref: str, path: str, max_bytes: int) -> dict[str, Any]:
    commit = resolve(run, ref)
    spec = f"{commit}:{path}"
    code, kind, _ = run(["git", "cat-file", "-t", spec])
    if code != 0:
        raise RunnerError("not_found", f"{path} does not exist at {ref}")
    if kind.strip() != "blob":
        raise RunnerError("invalid", f"{path} is a {kind.strip()}, not a file")
    _, size_out, _ = run(["git", "cat-file", "-s", spec])
    size = int(size_out.strip() or 0)
    body: dict[str, Any] = {
        "ref": ref,
        "commit": commit,
        "path": path,
        "size": size,
        "binary": False,
        "too_large": size > max_bytes,
        "content": None,
    }
    if body["too_large"]:
        return body
    code, content, err = run(["git", "cat-file", "blob", spec])
    if code != 0:
        raise RunnerError("internal", f"git cat-file: {err.strip()[-500:]}")
    if looks_binary(content):
        body["binary"] = True
        return body
    body["content"] = content
    return body
