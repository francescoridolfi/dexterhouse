## Unreleased

### Feat

- **observability**: alert metrics, Prometheus rules and a monitoring profile
- **deploy**: compose.prod.yaml with Caddy TLS and read-only core containers
- **api**: OpenAPI 3.1 at /api/v1/openapi.json and a tokens command
- **api**: Idempotency-Key on the POSTs that create resources
- **api**: rate limits on REST and WebSocket (T7, T16)
- Recruiter agent and marketplace client (E-08) (#13)
- registry CI commands, opt-in install telemetry and authors guide (E-11) (#12)
- runner and sandbox (E-05) (#10)
- **packages**: package system and installer (E-07) (#11)
- 2D dashboard, costs and observability (E-10)
- **workflows**: human in the loop backend (E-06) (#7)
- built-in agents (E-04) (#6)
- **workflows**: integrate the agents runtime with the workflow engine (E-02/E-03)
- **agents**: agents runtime, LLM gateway providers and project memory (E-03)
- **workflows**: projects domain and workflow engine (E-02) (#4)

### Fix

- **runner**: reconcile only the workspaces of this installation
- **agents**: escalate to a human when a turn is blocked for security violations
- **deploy**: give the worker network egress for LLM providers and packages
- **projects**: surface project.* and skills.read tool errors to the agent

### Perf

- fast and slow CI test suites, one MCP process per turn
