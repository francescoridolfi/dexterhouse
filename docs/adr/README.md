# Architecture Decision Records

This folder records the main architecture decisions of DexterHouse. Each ADR uses a reduced MADR format: context, decision, alternatives considered, consequences. Statuses: `proposed`, `accepted`, `deprecated`, `superseded by ADR-xxxx`.

| ID | Title | Status | Date |
|---|---|---|---|
| [ADR-0001](0001-stack-django-celery-redis-postgres.md) | Stack: Django, Celery, Redis, PostgreSQL in Docker Compose | accepted | 2026-10-31 |
| [ADR-0002](0002-declarative-packages.md) | Agents, tools and processes as declarative packages | accepted | 2026-10-31 |
| [ADR-0003](0003-mcp-for-tools.md) | MCP as the only protocol for tools | accepted | 2026-10-31 |
| [ADR-0004](0004-processes-as-state-machines.md) | Processes as YAML state machines | accepted | 2026-10-31 |
| [ADR-0005](0005-event-bus-redis-streams.md) | Event bus on Redis Streams with Postgres persistence | accepted | 2026-10-31 |
| [ADR-0006](0006-separate-runner.md) | Separate runner service with exclusive Docker socket access | accepted | 2026-10-31 |
| [ADR-0007](0007-spa-react-r3f.md) | Frontend SPA with React + React Three Fiber | accepted | 2026-10-31 |
| [ADR-0008](0008-multi-provider-llm-gateway.md) | Multi-provider LLM gateway with model profiles | accepted | 2026-10-31 |
| [ADR-0009](0009-agpl-license-with-cla.md) | AGPL-3.0 license with CLA | accepted | 2026-10-31 |
| [ADR-0010](0010-github-registry-and-marketplace.md) | Registry on GitHub + separate marketplace site | accepted | 2026-10-31 |
| [ADR-0011](0011-hybrid-execution-mode.md) | Hybrid execution mode per project | accepted | 2026-10-31 |
| [ADR-0012](0012-pre-commit-quality.md) | Code quality and security via pre-commit | accepted | 2026-10-31 |
| [ADR-0013](0013-persisted-state-idempotent-turns.md) | Agent state in Postgres, idempotent turns | accepted | 2026-10-31 |
| [ADR-0014](0014-agent-skills-format.md) | Skills in the Agent Skills format (SKILL.md) | accepted | 2026-10-31 |
| [ADR-0015](0015-organization-as-root.md) | Organization as the root of every entity | accepted | 2026-10-31 |
| [ADR-0016](0016-runner-without-secrets.md) | The runner holds no secrets and writes no events | accepted | 2026-10-31 |
| [ADR-0017](0017-code-graph.md) | A code dependency graph for the agents | accepted | 2026-11-14 |
