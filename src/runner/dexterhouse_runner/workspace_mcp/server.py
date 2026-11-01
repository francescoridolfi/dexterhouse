# SPDX-License-Identifier: AGPL-3.0-or-later
"""The MCP server: one tool per permission of the `workspace` and `git` tool packages.

Configuration comes from the container environment set by the runner (`DH_WORKSPACE_ROOT`,
`DH_WORKSPACE_QUOTA`, `DH_TEST_COMMAND`, `DH_LINT_COMMAND`, `DH_STACK_ENV_KEYS`,
`DH_SERVICES`). Tools run in a worker thread so a long `exec` never blocks the session.
"""

import inspect
import sys
from collections.abc import Callable
from typing import Annotated, Any

import anyio
from mcp.server.mcpserver import MCPServer
from pydantic import Field

from dexterhouse_runner.workspace_mcp import files, gitops, shell
from dexterhouse_runner.workspace_mcp.base import Config, ToolFailure


def _call(function: Callable[..., dict], *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        return function(*args, **kwargs)
    except ToolFailure as exc:
        return exc.as_dict()
    except OSError as exc:
        return {"error": {"code": "internal", "detail": f"{type(exc).__name__}: {exc}"}}


async def _run(function: Callable[..., dict], *args: Any, **kwargs: Any) -> dict[str, Any]:
    return await anyio.to_thread.run_sync(lambda: _call(function, *args, **kwargs))


def build_server(cfg: Config) -> MCPServer:
    server: MCPServer = MCPServer("dexterhouse-workspace", version="0.1.0")
    tool = server.tool

    @tool(name="workspace_list", description="Tree of the workspace with sizes.")
    async def workspace_list(path: str = ".", depth: int = 2, include_hidden: bool = False) -> dict:
        return await _run(files.list_tree, cfg, path, depth, include_hidden)

    @tool(name="workspace_read", description="Read a file (64 KB at most; use line ranges).")
    async def workspace_read(
        path: str, start_line: int | None = None, end_line: int | None = None
    ) -> dict:
        return await _run(files.read, cfg, path, start_line, end_line)

    @tool(name="workspace_search", description="Regex search with file, line and context.")
    async def workspace_search(
        pattern: str, path: str = ".", glob: str | None = None, max_results: int = 100
    ) -> dict:
        return await _run(files.search, cfg, pattern, path, glob, max_results)

    @tool(name="workspace_write", description="Create or overwrite a file.")
    async def workspace_write(path: str, content: str, create_dirs: bool = True) -> dict:
        return await _run(files.write, cfg, path, content, create_dirs)

    @tool(name="workspace_edit", description="Replace `old` (must occur `occurrences` times).")
    async def workspace_edit(path: str, old: str, new: str, occurrences: int = 1) -> dict:
        return await _run(files.edit, cfg, path, old, new, occurrences)

    @tool(name="workspace_delete", description="Delete a file or directory.")
    async def workspace_delete(path: str) -> dict:
        return await _run(files.delete, cfg, path)

    async def workspace_move(**kwargs: str) -> dict:  # `from` is a Python keyword
        return await _run(files.move, cfg, kwargs.get("from", ""), kwargs.get("to", ""))

    workspace_move.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        [
            inspect.Parameter(
                "from_",
                inspect.Parameter.KEYWORD_ONLY,
                annotation=Annotated[str, Field(alias="from")],
            ),
            inspect.Parameter("to", inspect.Parameter.KEYWORD_ONLY, annotation=str),
        ],
        return_annotation=dict,
    )
    tool(name="workspace_move", description="Move or rename a file.")(workspace_move)

    @tool(name="workspace_exec", description="Run a shell command (no TTY, timeout).")
    async def workspace_exec(
        command: str, cwd: str = ".", timeout_s: int = 120, env: dict[str, str] | None = None
    ) -> dict:
        return await _run(shell.run, cfg, command, cwd, timeout_s, env)

    @tool(name="workspace_run_tests", description="Run the stack's tests with a summary.")
    async def workspace_run_tests(
        scope: str = "all", path: str | None = None, timeout_s: int = 900
    ) -> dict:
        return await _run(shell.run_tests, cfg, scope, path, timeout_s)

    @tool(name="workspace_services", description="Declared services and their state.")
    async def workspace_services() -> dict:
        return await _run(shell.services, cfg)

    @tool(name="workspace_open_port", description="Internal URL of a port, for smoke tests.")
    async def workspace_open_port(port: int) -> dict:
        return await _run(shell.open_port, cfg, port)

    @tool(name="git_status", description="Changed and untracked files, current branch.")
    async def git_status() -> dict:
        return await _run(gitops.status, cfg)

    @tool(name="git_diff", description="Unified diff between refs (base...head).")
    async def git_diff(
        base: str = "main", head: str = "HEAD", path: str | None = None, stat_only: bool = False
    ) -> dict:
        return await _run(gitops.diff, cfg, base, head, path, stat_only)

    @tool(name="git_log", description="Commits with hash, author and message.")
    async def git_log(max: int = 20, path: str | None = None) -> dict:
        return await _run(gitops.log, cfg, max, path)

    @tool(name="git_show", description="A file at a ref, or a commit.")
    async def git_show(ref: str, path: str | None = None) -> dict:
        return await _run(gitops.show, cfg, ref, path)

    @tool(name="git_add", description="Stage paths.")
    async def git_add(paths: list[str]) -> dict:
        return await _run(gitops.add, cfg, paths)

    @tool(name="git_commit", description="Commit (Conventional Commits, detect-secrets).")
    async def git_commit(message: str, all: bool = False, author: str = "Agent") -> dict:
        return await _run(gitops.commit, cfg, message, all, author)

    @tool(name="git_checkout_file", description="Restore a file from a ref.")
    async def git_checkout_file(path: str, ref: str = "HEAD") -> dict:
        return await _run(gitops.checkout_file, cfg, path, ref)

    @tool(name="git_stash", description="Stash the working tree changes.")
    async def git_stash() -> dict:
        return await _run(gitops.stash, cfg)

    @tool(name="git_stash_pop", description="Restore the last stash.")
    async def git_stash_pop() -> dict:
        return await _run(gitops.stash_pop, cfg)

    return server


def main() -> int:
    cfg = Config.from_env()
    if not cfg.root.is_dir():
        sys.stderr.write(f"dexterhouse-workspace-mcp: {cfg.root} is not a directory\n")
        return 1
    build_server(cfg).run("stdio")
    return 0
