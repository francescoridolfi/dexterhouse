# SPDX-License-Identifier: AGPL-3.0-or-later
"""`dexterhouse-workspace-mcp`: the `workspace.*` and `git.*` tools inside a workspace.

The runner starts it with `docker exec -i <container> dexterhouse-workspace-mcp` and keeps
the stdio session open (infra/runner_protocol.md). It runs as uid 1000 in the container and
only needs the standard library, `mcp` and `detect-secrets`: the workspace images install
this subpackage alone, never the runner (no Celery, no Docker SDK inside a sandbox).

Every tool returns a JSON object; a failure is `{"error": {"code", "detail"}}` with a code
of `dexterhouse_schema.runner.ErrorCode`, which the runner turns into a `ToolResult`.
Paths are relative to the workspace root; `..`, absolute paths, symlinks leading out and
writes under `.git/` are `workspace_escape` (contracts/tools/workspace.md, git.md).
"""
