# dexterhouse-runner

The only DexterHouse service with access to the Docker socket (ADR-0006). It never imports the
core, holds no secret but the runner key and never writes events: it consumes the `runner`
Celery queue and answers through the result backend and the `core-callbacks` queue, with the
payloads of `dexterhouse_schema.runner`.

- `service.py`: what each message does (workspace lifecycle, tool calls, branches, merges, exit
  checks, delivery, heartbeat); `tasks.py`: the Celery app (`dexterhouse-runner worker`).
- `docker_manager.py`: the hardened workspace container (uid 1000, `cap_drop ALL`,
  `no-new-privileges`, read-only rootfs, CPU/RAM/pids limits), its internal network
  `dh_sandbox_<id>` with the egress proxy, its volume and the `stack.services` sidecars.
- `sessions.py`: one MCP stdio session per workspace through `docker exec -i`.
- `workspace_mcp/`: `dexterhouse-workspace-mcp`, the `workspace.*` and `git.*` tools that run
  inside the workspace image (standard library, `mcp` and `detect-secrets` only).
- `delivery.py` and `grants.py`: the release push with a one-time grant and `GIT_ASKPASS`,
  never in the workspace and never forced; pull requests through the GitHub or GitLab API.

Prometheus metrics on `RUNNER_METRICS_PORT` (9100). Configuration: `.env.example`, section
Workspaces.
