# Writing a process

A process package says which phases a project goes through, which agent runs each phase,
what each phase must produce, and where a human decides. It is a `process.yaml` next to the
`dexterhouse.yaml` manifest ([authors.md](authors.md) covers the manifest, validation and
publishing). The core runs it as a state machine ([ADR-0004](adr/0004-processes-as-state-machines.md)).

```bash
dexterhouse pkg init my-process --kind process
```

## A minimal process

```yaml
schema: 1
name: code-review-only
version: 1.0.0
phases:
  - id: review
    agent: reviewer
    workspace: true
    produces: [review]
    exit: artifacts_present
    gate: { id: approve_review, default: optional }
```

## Phases

| Key | Meaning |
|---|---|
| `id` | unique in the process |
| `needs` | phases that must complete first; the graph must be acyclic |
| `agent` **or** `steps` | one role, or a sequence of `{agent, step?, produces?, exit?, command?}` |
| `produces` | artifact kinds the phase must leave (`requirements`, `user_stories`, `architecture`, `adr`, `stack`, `task_board`, `team_proposal`, `review`, `test_report`, `release_notes`, `retrospective`, …) |
| `exit` | what the core verifies before the phase ends: `artifacts_present`, `tests_pass` (runs the stack's test command), `command_ok` (runs `command`), `none` |
| `may_ask` | the agent may open a question gate (only in `supervised` mode) |
| `workspace` | the phase needs a workspace; an earlier phase in `needs` must produce `stack`, or the project must give one |
| `gate` | `{id, default: required\|optional, on_approve: [...], on_reject: ...}` |
| `after_gate` | steps run after the gate, with `when: hired\|always\|never` |
| `type: loop` | repeat `steps` for each item of `over` (`task_board`), one at a time; needs `max_iterations` (1–10) and `on_exhausted: escalate\|fail` |

Roles are the agent packages installed for the organization (the built-in seven:
`analyst`, `architect`, `project_manager`, `recruiter`, `developer`, `reviewer`,
`tester`). They are checked when a project starts, not when the process is installed.

## Gates and actions

- `default: required` waits for a human in `supervised` mode; in `autonomous` mode only a
  project's *always required* override makes a gate wait. `optional` never waits unless
  overridden.
- `on_approve` may run `install_proposed_packages`, `hire`, `merge` and `deliver` (push or
  pull request, per the project's `delivery_mode`); `on_reject` may be
  `reopen_implementation` or `fail`. Without `on_reject`, a rejection reruns the phase with
  the comment, at most twice.
- Escalations for budget, loops and permissions are added by the core to every process and
  cannot be removed.

## Rooms

`rooms: {phase_id: room}` places a phase in a room of the 3D office (`meeting_room`,
`release_dock`, …); without it the agent's own room is used ([office.md](office.md)).

## Example: the default process

The built-in `software-house-default` (in `src/builtin/processes/`) is a complete example:
analysis with questions, architecture producing the `stack`, planning with the Recruiter and
an `approve_plan` gate that installs and hires, a develop → review → test loop over the
task board with at most 3 rounds per task, a release phase whose steps run the integration
tests and a smoke command before `approve_release` delivers, and a retrospective.

Validate with `dexterhouse-schema validate .`: it checks the keys above, that `needs`
references exist and form no cycle, and that loops and exits are complete.
