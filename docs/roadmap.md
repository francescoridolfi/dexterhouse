# Roadmap

DexterHouse is being designed in the open. Dates are indicative; the order is the commitment.

## 1.0 — "The office opens"
- Full pipeline: brief → requirements → architecture → plan → iterative implementation (develop, review, test) → integration → release → retrospective.
- Seven built-in agents: Analyst, Architect, Project Manager, Recruiter, Developer, Reviewer, Tester.
- `supervised` and `autonomous` execution modes with approval, question and escalation gates.
- Multi-provider LLM gateway: Anthropic (API and Claude Code CLI), OpenAI, OpenAI-compatible endpoints, Ollama. Model profiles instead of hard-coded models.
- Isolated runner and per-project workspace sandboxes with egress allow-list.
- Declarative packages (agents, tools over MCP, processes, skills) and the public registry + marketplace with the Recruiter agent proposing packages during planning.
- 3D office view driven by the event stream, with replay; full 2D dashboard, live logs, costs and budgets.
- Delivery to your repository as a pull request or push.
- REST API, WebSocket, CLI; Prometheus metrics; one-command Docker Compose install.

## 1.x — "More desks"
- Parallel implementation of independent tasks (git worktrees) with conflict resolution step.
- Organization-wide memory ("lessons learned" across projects).
- Package signing (sigstore) and signature verification at install.
- Optional gVisor runtime for the sandbox.
- Webhooks and integrations: Slack/Discord notifications for gates, GitHub Checks on delivered PRs.
- Simple conditions in processes (`when:`), sub-processes, more built-in processes (Kanban, audit-only, docs-only).
- Localized UI (Italian first), accessibility audit of the 3D office.
- Custom avatars and office themes; sponsor-driven art.

## 2.0 — "The agency"
- Multi-tenant hosting mode and billing, for teams that prefer not to self-host (the core stays AGPL; a commercial license will be available).
- Visual process editor.
- Cross-project agents (an agent that follows a product across repositories).
- Plugin API for runtime extensions, once a safe isolation model is proven.

## Not planned
Deploying the software the agents produce to production; replacing your CI; mobile apps.

Have a say: open a Discussion, or vote on the pinned roadmap issues.
