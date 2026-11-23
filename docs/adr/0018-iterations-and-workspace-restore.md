# ADR-0018: Process iterations and workspace restore for change requests

- Status: accepted · Date: 2026-11-23 · Spec: [change-requests](../specs/change-requests.md)

## Context
A project runs one `ProcessRun` (one-to-one) and ends in `completed`, which only leads to
`archived`. Change requests (CR) must run the whole process again on the delivered product.
The workspace is destroyed 24 h after completion, and the core never reads workspaces
(ADR-0006), so the code must be restorable without the core holding it.

## Decision
- **Iterations.** `ProcessRun.project` becomes a foreign key; `ProcessRun.iteration`
  (0 = brief, n = CR-n) is unique per project. `common.lock(project_id)` returns the run
  with the highest iteration; nothing else reads `project.process_run` directly
  (`Project.current_run` for read-only callers). `Task` gets a `process_run` foreign key and
  its unique key becomes `(process_run, external_id)`. Migrations are expand-only: existing
  rows get `iteration = 0` and their run.
- **Reopening.** `completed → running` exists in the project state machine but only
  `start_change_request` calls it; it creates the next iteration's run and emits
  `project.reopened {change_request, iteration}`.
- **Snapshot.** When an iteration completes, the core sends `runner.system.snapshot`:
  the runner writes `git bundle create <dir>/<project_id>.bundle --all` into its own
  volume (`RUNNER_SNAPSHOT_DIR`, default `/data/snapshots`), replacing the previous one.
- **Restore.** `WorkspaceCreate` gains an optional `restore`. With `source: snapshot` the
  runner clones the project's bundle into the new volume; with `source: remote` it clones
  `branch` from `remote_url` with the token of a `SecretGrant` (`token_ref`), as delivery
  does. The result carries `restored_commit`. The core tries the snapshot, then the remote;
  if both fail the workspace fails and opens the usual `workspace_error` escalation.
- **Forget.** `runner.system.snapshot_drop {project_id}` deletes the bundle; the core sends
  it when the project is archived.

## Contract (`dexterhouse_schema.runner`)

```python
class Snapshot(Message):  # runner.system.snapshot -> ToolResult.data {commit, size}
    workspace_id: uuid.UUID
    project_id: uuid.UUID


class SnapshotDrop(Message):  # runner.system.snapshot_drop -> ToolResult.data {deleted}
    project_id: uuid.UUID


class Restore(Message):
    source: Literal["snapshot", "remote"]
    remote_url: str | None = None
    token_ref: uuid.UUID | None = None  # SecretGrant id, never a token
    branch: Branch = "main"


class WorkspaceCreate(Message):  # + restore; WorkspaceChanged gets restored_commit
    ...
    restore: Restore | None = None
```

## Alternatives considered
- Keep workspaces of completed projects forever: disk grows with every project.
- The core stores the bundle: it would read workspace content, against ADR-0006.
- Clone from the remote only: projects without a repository, or with an unmerged pull
  request, would lose their code.

## Consequences
+ A CR starts from exactly the code of the last iteration, with its history.
+ Earlier iterations' runs, tasks and events stay as they were.
− One bundle per project on the runner volume (size of the repository); dropped on archive.
− Every reader of the run goes through `common.lock` or `Project.current_run`.
