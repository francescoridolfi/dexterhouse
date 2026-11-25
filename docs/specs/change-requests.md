# Spec: change-requests

Shared commands, style and boundaries: [README.md](README.md). Depends on
[context-documents.md](context-documents.md).

## Objective

Today a `completed` project can only be archived: asking for further changes means a new
project that has lost the history. A **change request (CR)** reopens the project and runs
the whole process again on the existing product, like a brief does, then delivers a new
release. Users: `member` writes CRs, `admin` starts them (same split as gates).

## Design

- **Model** `ChangeRequest` (projects app): `project`, `number` (CR-1, CR-2, … per project),
  `title` (≤ 120), `body` (≤ 20 000, Markdown), `budget` (EUR, ≥ 0, added to the project
  budget when it starts), `status`, `created_by`, `started_at`, `completed_at`,
  `process_run` (set when it starts). On start the body is saved as an artifact of the new
  kind `change_request` (`cr-<n>.md`) and indexed in memory.
- **CR states**: `draft → queued → running → completed | failed`, `draft|queued → cancelled`,
  `failed → running` (retry). Only `draft` is editable. At most one CR `running` per project.
- **Starting** (D3): queuing a CR on a `completed` project starts it at once; queuing it on an
  active project leaves it `queued`. When an iteration completes, the oldest `queued` CR
  starts automatically. Drafts never start by themselves.
- **Iterations**: `ProcessRun` becomes one-to-many with `iteration` (0 = brief, n = CR-n),
  unique on `(project, iteration)`; `project.process_run` becomes "latest run" through a
  helper (`common.lock` returns it). `Task` gets a `process_run` FK and its unique key
  becomes `(process_run, external_id)`, so a new task board can reuse `T-001`. The process
  version used is the one installed at start time.
- **Project state machine**: new transition `completed → running`, allowed only through
  `start_change_request` (not `PATCH`, not the header buttons). `completed_at` is set again
  when the iteration ends. `failed` during a CR is retried with the existing *Retry*.
- **Agent inputs** (iteration > 0): every step also reads `change_request` (current CR) and
  the latest `release_notes`; the analyst additionally reads the current `requirements`,
  `user_stories`, `architecture`, `stack` and `code_graph` summary; documents attached to the
  CR are read before the others. The built-in prompts get an iteration guide: "this is CR-n
  on a delivered product: change what the CR asks, keep the rest, write requirements as a new
  version that marks added/changed/removed items". Earlier artifacts stay as older versions.
- **Gates and mode**: as configured on the project; the mode can be switched before starting.
- **Workspace**: reused if still live; otherwise recreated and the code restored before the
  first workspace turn (see Q1). A failure opens a `workspace_error` escalation.
- **Delivery**: unchanged mechanism; `release_number` already counts deliveries, so CR-1 is
  delivered as `dexterhouse/release-2`, with "CR-1: <title>" in the PR title and body.
- **Memory and costs**: retrospective lessons of earlier iterations keep their weight; the
  Costs tab gains an iteration filter (brief, CR-1, …); `budget.estimated` is emitted per CR.

## API (REST v1)

| Method | Path | Role |
|---|---|---|
| `GET`/`POST` | `/projects/{id}/change-requests` | viewer / member |
| `GET`/`PATCH` | `/change-requests/{cr_id}` (PATCH only in `draft`) | viewer / member |
| `POST` | `/change-requests/{cr_id}/queue` · `/cancel` | admin |
| `GET` | `/change-requests/{cr_id}/estimate` | member |

Events: `change_request.created|updated|queued|started|completed|failed|cancelled`; the
project emits `project.reopened` with `{change_request, iteration}`.

## UI

- Project page: new **Changes** tab: list of CRs (number, title, status, budget, cost,
  release link), *New change request* form (title, Markdown body, budget, attachments via
  the context upload), *Estimate*, *Queue/Start*, *Cancel*.
- Header: "CR-2 · running" next to the status; Overview phases show the current iteration
  with a selector for past ones (read-only).

## Acceptance criteria

1. On a `completed` project an admin queues CR-1: the project goes `running`, a new
   `ProcessRun` with `iteration=1` starts at `analysis`, `project.reopened` is emitted.
2. The analyst's turn of CR-1 lists `change_request`, previous `requirements` and attached
   documents in its `context_manifest`.
3. After `approve_release`, CR-1 is `completed` and the delivery uses `release-2`.
4. A CR queued while the project is `running` stays `queued` and starts by itself when the
   project completes; two queued CRs run one after the other in `number` order.
5. Iteration 0 artifacts, tasks and events are unchanged and still readable.
6. A `member` can create and edit a draft but not queue it (403); a non-draft CR cannot be
   edited (`invalid_transition`); an archived project refuses new CRs.
7. The CR budget is added to the project budget on start (`project.budget_changed`).
8. Existing single-run projects work unchanged after the migration (data migration sets
   `iteration=0`, backfills `Task.process_run`).

## Tests

`src/core/tests/projects/test_change_requests.py` (states, roles, queue),
`src/core/tests/workflows/test_iterations.py` (migration, lock helper, task keys),
`test_inputs_iteration.py`, a slow e2e with the fake runner (brief → release-1 → CR-1 →
release-2). Frontend: `ChangesTab.test.tsx`, Playwright path on the demo project.

## Open questions

- Q1. **Restoring code** when the workspace was destroyed (24 h after completion). Proposal:
  at completion the runner stores a `git bundle` of `main` in the core volume; a CR restores
  from it, and falls back to cloning the delivered branch from `remote_repo_url`. Needs a
  runner protocol change and an ADR.
- Q2. Should a CR be able to change the process or stack (e.g. move to another process)?
  Proposal: no in v1; the project's process is fixed.
- Q3. Auto-start of a queued CR in `autonomous` mode spends money without a click: keep it,
  or require the org budget check only? Proposal: keep, with the usual budget guards.

## Implementation notes (E-13)

- `iteration` equals the CR number: a cancelled CR leaves a gap (CR-2 after a cancelled
  CR-1 runs as iteration 2).
- Reopening clears `completed_at`; it is set again when the iteration completes.
  `project.budget_changed` also has the `system` actor (a CR started from the queue).
- Q1 closed by ADR-0018: snapshot in the runner, restore from it, then from the last
  delivered branch. Q2 and Q3 as proposed.
- Not yet: the CR JSON has no release link; archiving does not cancel draft or queued CRs.
