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
| `room`, `mode`, `may_ask`, `data_residency` (`any`/`local`), `verdict_rule` (`review`/`test`/`none`) | behaviour and output rules |
| `known_finding_ids`, `installed_roles`, `task_ids`, `stack_test_command` | TurnOutput validation context |

## Still to wire

- Budget checks before the call and `Project.spent` updates (F-012, E-10).
- The real built-in agent packages and prompts (E-04); tests use
  `src/core/tests/fixtures/agent_packages/`.
