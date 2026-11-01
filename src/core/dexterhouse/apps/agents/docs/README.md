# Agents runtime: how the workflow engine runs a turn

This app owns `AgentInstance`, `AgentTurn` and `ToolCall`. Turns point to their project,
phase run, task and step run (foreign keys), but what a turn needs to *read* from them
arrives as `TurnInputs`; a completed turn stores its output artifacts as `Artifact` rows.

## API (`dexterhouse.apps.agents.services`)

```python
create_agent_instance(*, organization_id, project_id, package_path, granted_tools=None,
                      display_name=None, source="builtin", room=None,
                      package_version_id=None) -> AgentInstance
queue_turn(*, agent: AgentInstance, purpose: str, inputs: TurnInputs | dict,
           phase_run_id=None, task_id=None, step="", enqueue=True,
           step_run_id=None, attempt=1) -> AgentTurn
run_turn(turn_id: uuid.UUID) -> dexterhouse_schema.TurnOutput
cancel_turn(turn_id: uuid.UUID, reason: str) -> bool
```

- `create_agent_instance` loads the agent package (`agent.yaml`), sets `allowed_tools` to
  the package tools ∩ `granted_tools` and emits `agent.hired`.
- `queue_turn` stores the turn as `queued`, emits `agent.turn.queued` and, on commit, sends
  the Celery task `dexterhouse.apps.agents.tasks.run_turn` to the `agents` queue
  (`enqueue=False` to run it yourself). With `step_run_id`, the same `(step_run_id, attempt)`
  returns the turn already created for it: queueing is idempotent too.
- `run_turn` builds the context, calls the LLM through the gateway, executes tool calls over
  MCP and returns the validated `TurnOutput` (the turn is then `completed`). It is
  idempotent: calling it again resumes a `running` turn from the last persisted message and
  returns the stored output of a `completed` one. It raises `AgentTurnFailedError`
  (`error_code`: output_contract, tool_limit, timeout, provider, permission,
  context_overflow, configuration) or `TransientTurnError` (provider or tool server down: the
  turn stays resumable and the Celery task retries with backoff).

The workflow engine uses them through `AgentsTurnRunner`
(`dexterhouse/apps/workflows/runners/agents.py`), selected with
`WORKFLOWS_TURN_RUNNER`: one step run is one turn, created with
`queue_turn(step_run_id=..., attempt=..., enqueue=False)` and run synchronously in the
`run_step` worker (queue `agents`). A retry resumes the previous attempt's turn while it is
`queued` or `running`; only a `failed` turn gets a new one. The mapping
`TurnRequest -> TurnInputs` is `workflows/runners/inputs.py`.

## The team (`services/roster.py`)

- `ensure_agent(project, role)`: the active agent of the role, hired on first use from the
  first package for the role in `settings.AGENTS_PACKAGE_DIRS` (built-in, then installed);
  without a package, a *placeholder* agent (no package, no tools) that only
  `FakeTurnRunner` can run. The built-in team uses the stable id `team_agent_id(project, role)`.
- `hire_team`: the process start hires one agent per process role.
- `hire_proposed`: the `hire` system action, one agent per accepted `team_proposal` entry
  whose package is installed, `allowed_tools` = package tools ∩ proposal permissions.

## `TurnInputs` (`dexterhouse.apps.agents.schemas`)

| Field | Context section |
|---|---|
| `step_description`, `task` (`TaskInput`: external_id, title, description, acceptance, iteration, max_iterations, files_hint, status) | 6 task / step |
| `gate_answers` (most recent first) | 7 |
| `review_items` (open findings or test failures, as JSON) | 8 |
| `artifacts` (`ArtifactInput`: id, kind, name, version, `content` or `data`, untrusted) in phase order | 9 |
| `notes` (`NoteInput`: id, text), most recent first | 11 |
| `workspace_tree` (indented text, two spaces per level) | 12 |
| `memory_query` (default: task title + acceptance) | 10 |
| `produces` (artifact kinds the step asks for) | step description, demo responder |
| `room`, `mode`, `may_ask`, `data_residency` (`any`/`local`), `verdict_rule` (`review`/`test`/`none`) | behaviour and output rules |
| `known_finding_ids`, `installed_roles`, `task_ids`, `stack_test_command` | TurnOutput validation context |

## Tools a turn cannot reach

An agent's `allowed_tools` may name tools the core cannot reach yet: a permission no
installed tool package exposes (`workspace.*`, `git.*`, `marketplace.*`, `packages.*` until
E-05, E-07 and E-08), a `runs_in: runner` tool before the runner exists, or a server that
does not start or does not list the tool. The turn does not fail: the tool is left out of
the tool schemas sent to the model, a warning `agents.tools_unavailable` is logged, and
`AgentTurn.context_manifest.unavailable_tools` maps each one to `not_installed`,
`runs_in_runner`, `server_unavailable` or `missing_on_server`. A call to it anyway gets a
`tool_unavailable: <tool> (<reason>)` error result, not a refusal (no `security.violation`).
Skills whose `tools_required` are unavailable are not listed. `packages.install` is offered
only in autonomous mode.

## Argument policies

A call is checked against the tool package's `permissions[].args_policy` and the agent's
own `agent.yaml` `args_policy` (CD-032: the built-in tester writes only test paths, the
developer cannot touch `tests/acceptance/`). The agent's policy is checked first, even for
an unreachable tool, so a forbidden write is a `security.violation(args_policy)`.

## Built-in agents and the demo responder

The seven built-in packages live in `src/builtin/agents/`; the skills every agent may load
in `src/builtin/skills/` (listed when the agent has their `tools_required`).
`dexterhouse.apps.agents.demo.respond` answers the gateway's `fake` provider as the built-in
agents would, by role and step, from the turn's `TurnInputs`: set
`GATEWAY_FAKE_RESPONDER=dexterhouse.apps.agents.demo.respond` and the organization's model
profiles to provider `fake` to run a whole project without any LLM. `AGENTS_DEMO_SCRIPT`
scripts it (`ask_questions`, `tasks`, `hire`, `verdicts`; see the module).

## Still to wire

- Budget checks before the call and `Project.spent` updates (F-012, E-10).
