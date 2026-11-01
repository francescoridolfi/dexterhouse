# Agents runtime: how the workflow engine runs a turn

This app owns `AgentInstance`, `AgentTurn` and `ToolCall`. It knows nothing about projects,
phases or tasks beyond their ids: what a turn needs from them arrives as `TurnInputs`.

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

A synchronous `TurnRunner` (E-02) can therefore be:

```python
turn = queue_turn(
    agent=agent,
    purpose=step.purpose,
    inputs=inputs,
    phase_run_id=phase_run.id,
    task_id=task.id,
    step=step.id,
    enqueue=False,
)
output = run_turn(turn.id)  # TurnOutput
```

or asynchronous: `queue_turn(...)` and react to `agent.turn.completed` / `agent.turn.failed`
(`AgentTurn.output` holds the TurnOutput JSON).

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

## What the integration still has to wire

- Foreign keys: every `# FK added at integration (E-02)` uuid becomes a FK to `Project`,
  `PhaseRun` or `Task`.
- Storing `TurnOutput.artifacts` as `Artifact` rows (and indexing them with
  `dexterhouse.apps.memory.tasks.index_artifact`), then filling `agent.turn.completed.artifacts`.
- Budget checks before the call and `Project.spent` updates (F-012).
- `project.*` and `skills.read` MCP tools (contracts/tools/memory.md) need the projects app.
