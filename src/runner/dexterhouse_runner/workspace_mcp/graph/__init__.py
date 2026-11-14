# SPDX-License-Identifier: AGPL-3.0-or-later
"""`workspace.graph`: a deterministic dependency graph of the workspace (no LLM calls).

- :mod:`.scan` lists the source files (git index + untracked, minus vendored and build dirs);
- :mod:`.lang_python` reads Python with the standard library's `ast`;
- :mod:`.lang_regex` reads JS/TS, Go and Java with line regexes (the workspace images ship
  no tree-sitter: imports, top-level declarations and `extends` only, no method scopes);
- :mod:`.build` resolves imports, calls and bases into the `code_graph` artifact format,
  caching each file's facts by content hash (`.git/dexterhouse/code-graph-cache.json`);
- :mod:`.query` answers `summary`, `neighbors`, `path` and `find` compactly for the model.
"""

from dexterhouse_runner.workspace_mcp.graph.build import build_graph
from dexterhouse_runner.workspace_mcp.graph.query import GraphIndex

__all__ = ["GraphIndex", "build_graph"]
