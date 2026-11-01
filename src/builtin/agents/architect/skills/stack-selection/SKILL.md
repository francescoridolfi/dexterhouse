---
name: stack-selection
description: "Criteria to choose language, framework and services among the supported workspace images, and how to write stack.yaml commands. Use before writing stack.yaml."
dexterhouse:
  schema: 1
  tools_required: []
  cost_hint: low
  rooms: [design_studio]
---

# Stack selection

Supported images and what they contain:

| workspace_image | Toolchain | Typical stacks |
|---|---|---|
| dexterhouse/workspace:python | Python 3.12, uv, pip | Django, FastAPI, Flask |
| dexterhouse/workspace:node | Node 22, npm, pnpm | Express, Fastify, Next.js, Vite |
| dexterhouse/workspace:full | Python, Node, Go | mixed stacks, Go services |

Services available: postgres, redis, mailpit. Nothing else.

Criteria, in order: the client's declared constraints; what the team (agents) writes reliably; the fewest moving parts that meet the requirements; testability in a container without network.

stack.yaml rules:
- `test_command` runs the whole suite non-interactively and exits 0 or 1 (`uv run pytest -q`, `npm test --silent`).
- `run_command` binds 0.0.0.0 on a port in `ports` (1024-65535).
- `install_command` installs pinned dependencies (`uv sync --frozen`, `npm ci`).
- At most 300 characters per command, at most three `&&`, never `sudo`.
- Prefer SQLite in development when the requirements allow it; declare `postgres` in `services` only if needed.
