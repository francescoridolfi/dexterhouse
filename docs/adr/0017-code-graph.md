# ADR-0017: A code dependency graph for the agents

- Status: accepted · Date: 2026-11-14

## Context
Developers, reviewers and testers find their way in the workspace with `workspace.list/read/search`: to know where to change something they read whole files and spend thousands of tokens before writing a line. The `tree` section of the context (the file tree) says little about how files depend on each other.

## Decision
- **Deterministic** extraction inside the workspace MCP server (`workspace_mcp/graph/`), no LLM calls: Python with the standard library's `ast`; JS/TS, Go and Java with regexes over imports, top-level declarations and `extends`. The workspace images only install `mcp` and `detect-secrets`, so no tree-sitter.
- `.git`, `node_modules`, virtualenvs, caches and build folders are skipped; at most 5000 files of 1 MB.
- Per-file facts are cached by SHA-256 of the content, in memory and in `.git/dexterhouse/code-graph-cache.json` (never committed).
- The `workspace.graph` tool (risk low) answers `summary`, `neighbors`, `path` and `find`; developer, reviewer, tester and architect have it. The shared `code-graph` skill teaches graph first, then only the files needed.
- The `code_graph` artifact (`code_graph.json`, structured data, schema 1) is saved by the core after every successful agent `git.commit` (task `refresh_code_graph`, system call `runner.system.code_graph`); the same commit gives no new version; it is not indexed into the project memory.
- The context's `tree` section gets the graph summary within the profile's `tree` budget (2000/1500/800 tokens), cut by whole lines in priority order; the file tree remains the fallback.

## Alternatives considered
- LLM extraction: costly, not repeatable, unnecessary for code.
- tree-sitter in the images: more precise for JS/TS method scopes, but native dependencies in every image; deferred until the regexes show real limits.
- The core building the graph from the files: the core never reads workspaces (ADR-0006).

## Consequences
+ A graph answer costs hundreds of tokens, reading a file thousands.
+ The frontend gets one artifact version per commit to display.
− In JS/TS calls are attributed to the file, not the function; dynamic imports and dependency injection are not edges.
− Every agent commit stores the whole graph (a few MB on large projects); prune old versions if storage becomes an issue.
