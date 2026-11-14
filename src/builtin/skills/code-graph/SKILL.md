---
name: code-graph
description: "Find your way in the code with workspace.graph before reading files: the map of modules, the neighbours of a file or symbol, the path between two, file and line of a name. Use at the start of every coding, review or test task."
dexterhouse:
  schema: 1
  tools_required: [workspace.graph]
  cost_hint: low
  rooms: [open_space, review_corner, qa_lab, design_studio]
---

# Code graph

The workspace has a dependency graph built from the code itself (imports, definitions, calls,
inheritance, tests). It costs a few hundred tokens per answer; reading a file costs thousands.
The `# Workspace tree` section of your context already holds its summary when a workspace exists.

## Order of work
1. Orient: read the summary in your context; call `workspace.graph` (action `summary`) only if it
   is missing or you changed many files.
2. Locate: `find` with a class, function or file name returns the file and line.
   Ambiguous names list candidates: pick one by its id (`sym:path::Name`).
3. Expand: `neighbors` on the file or symbol shows what it imports, defines and calls (`out`)
   and who imports, calls or tests it (`in`). Use it to find the callers you may break and the
   tests to run.
4. Connect: `path` between two nodes explains how a change in one reaches the other.
5. Read: only then `workspace.read` the files you will change or must understand, with
   `start_line`/`end_line` around the line the graph gave you. Use `workspace.search` for
   text the graph does not hold (strings, config keys, SQL, templates).

## Rules
- Do not list or read whole directories to "get a feel" for the project: the summary does that.
- Never read a file just because the graph shows it as a neighbour; read it when you need its code.
- The graph is rebuilt from the working tree on every call: after your edits it is current.
- It is static analysis: dynamic imports, reflection, dependency injection and JS/TS method
  calls are not edges. When a call matters and has no edge, confirm it with `workspace.search`.
- Node ids: `file:<path>`, `module:<dir>`, `sym:<path>::<Class.method>`, `ext:<package>`.
  Plain paths and unique symbol names work too.
