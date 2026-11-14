# Using DexterHouse

A project goes from a brief to a delivered repository through the phases of a **process**.
The built-in `software-house-default` process:

| Phase | Agents | Produces | Gate |
|---|---|---|---|
| analysis | Analyst | requirements, user stories (may ask you questions) | `approve_requirements` |
| architecture | Architect | architecture, ADRs, `stack` (language, test and run commands) | `approve_architecture` |
| planning | Project Manager, then Recruiter | task board, team proposal | `approve_plan` (installs and hires the approved packages) |
| implementation | Developer → Reviewer → Tester, one task at a time | code and tests in the workspace | none; at most 3 rounds per task, then an escalation |
| release | Tester (integration, smoke), Project Manager | release notes | `approve_release` (delivers on approval) |
| retrospective | Project Manager | lessons for the project memory | none |

`code-review-only` is a second built-in process (one Reviewer pass on an existing
repository). Writing your own: [processes.md](processes.md).

## 1. Write the brief

*Projects → New project*: a name, the brief (what to build, for whom, constraints; up to
20 000 characters), the process, the mode, a budget in EUR, and optionally the repository
to deliver to. *Estimate* shows the expected cost before you start. Starting checks that
every role of the process has an agent and that the repository and token work.

The brief is the most important input: name the users, the must-have features, the stack
if you have one in mind, and what "done" means. The analyst turns it into requirements and
asks about the gaps.

## 2. Pick a mode

| Mode | Gates | Questions |
|---|---|---|
| `supervised` (default) | every `required` gate waits for you | the analyst asks, the project waits for answers |
| `autonomous` | gates are approved automatically, except those you mark *always required* | the agent states assumptions instead |

Escalations always wait for a human in both modes: a task that failed review or tests three
times, a turn that failed three times, a tool with `risk: high`, a security block, the
budget at 100 %. You can switch mode on a running project.

## 3. Decide gates

Open gates appear in the **Inbox** and on the project page, with the artifacts to read.

- **Approval** (admin): *Approve*, *Approve with comments* (the next agents read the
  comment), or *Reject* with a comment: the phase reruns with it, at most twice, then an
  escalation.
- **Questions** (member): answer every question; the analyst continues.
- **Escalation** (admin): *Retry* (after fixing the cause, e.g. raising the budget),
  *Accept* the current result, or *Drop* the task.

Every decision is recorded with who and when, and is part of the event log. Unanswered
gates are re-notified after the organization's TTL (in-app, and by email when configured).
You can also leave **notes** for the agents from the Overview tab; the next turn of the
phase reads them and the note shows who read it. The gate re-notification TTL
(`gate_ttl_hours`) and opt-in install telemetry are organization settings set through
`PATCH /api/v1/organization` ([api.md](api.md)).

## 4. Watch it work

The project page has tabs: **Overview** (phases, current step, open gates), **Board**
(tasks and their rounds), **Artifacts** (every version, with diffs), **Log** (live events
and what the agents are saying), **Costs**, **Team** (agents, their package and room) and
**Office** (the 3D view, see [office.md](office.md); hidden on small screens). Clicking an
agent's turn shows its inputs, tool calls, tokens and cost, and what it knew
(`context_manifest`).

Projects can be paused, resumed and retried from the header. The page reconnects by itself
and resynchronises after a network drop.

## 5. Delivery

On `approve_release` DexterHouse pushes the project's `main` to your repository: by default
to a `dexterhouse/release-<n>` branch with a pull request. Modes, token scopes and failure
reasons: [delivery.md](delivery.md). Agents never push; delivery is a system action.

## Budgets and costs

- **Project budget** (EUR): at 80 % you get a warning, at 100 % the project stops at the
  next LLM call and opens a `budget_exceeded` escalation. Raise the budget, then *Retry*.
- **Organization budget** (monthly, *Settings → Budget*): same thresholds across projects.
- Every LLM call is recorded with tokens, cost and latency; the **Costs** tab breaks them
  down by phase, task, agent and model. Prices: `prices.yaml` (override with `PRICES_FILE`),
  USD converted with `FX_EUR_PER_USD`.

The `fake` provider costs nothing; local models (Ollama) cost what you configure.

## Project memory

Artifacts, gate comments and notes are split into chunks and embedded with the `embed`
profile into pgvector. Agents query it with the `memory.search` tool (within the project,
retrospective lessons and your comments weigh more), so later phases find earlier
decisions without reading every document. Without an embedder the memory is off and agents
read artifacts directly. After changing the `embed` model run
`docker compose exec web dexterhouse-manage memory reindex --project <project_id>` (or `--all`).

## Code graph

Inside the workspace, agents read a dependency graph of the code before opening files: the
`workspace.graph` tool (developer, reviewer, tester, architect) answers with a map of the
project (main modules, most connected files and symbols, entry points), the neighbours of a
file or symbol, the path between two, and the file and line of a name. It is built from the
code itself, without any model: Python through its syntax tree, JS/TS, Go and Java through
their imports and declarations. Each agent commit saves it as the `code_graph` artifact
(`code_graph.json`), and its summary opens the context of every turn in the workspace.

## Data residency

A project with `data_residency: local` may only use providers marked local (Ollama, or an
OpenAI-compatible endpoint flagged *local*): a turn that would call a cloud provider is
refused before the call.

## Packages and the Recruiter

During planning the Recruiter searches the registry for agents and tools the plan needs
and proposes them at `approve_plan`; approving installs them and adds them to the team.
Manage installed packages in *Packages*: [packages.md](packages.md), [recruiter.md](recruiter.md).

## Settings

*Settings* holds the organization, members and roles
(`viewer` reads, `member` creates projects and notes, `admin` decides gates and manages
packages and profiles, `owner` manages members), model profiles, providers and the budget.
API tokens are created from the command line for now ([api.md](api.md#authentication)).
