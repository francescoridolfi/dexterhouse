# Specs: change requests and context documents

Status: **draft, awaiting approval** (2026-11-23). Two capabilities, one spec each; this page
is the index and holds what both share (commands, structure, style, boundaries).

## Capability map

| Module id | Responsibility | Depends on |
|---|---|---|
| `context-documents` | import external files (technical analyses, context), extract text, index in memory, feed agents | — |
| `change-requests` | add CRs to a project; a CR reopens a `completed` project and reruns the whole process as a new iteration, delivered as `release-<n+1>` | `context-documents` (a CR can attach documents) |

Build order: `context-documents` → `change-requests`.

- [context-documents.md](context-documents.md)
- [change-requests.md](change-requests.md)

## Decisions taken with the owner

| # | Decision |
|---|---|
| D1 | Two modules, two specs, built in the order above. |
| D2 | A CR reruns the **whole process** (analysis → retrospective) like a brief; the agents read the CR plus what already exists and produce a delta. |
| D3 | A CR **starts only from `completed`**; while the project is active it can be written as a draft or queued, and starts after the current iteration, one at a time. |
| D4 | Importable formats: text (`.md .txt .json .yaml .yml .csv`) plus **PDF and DOCX** converted to text on the server. |

## Commands

```bash
uv run pytest -m "not slow" src/core/tests/projects src/core/tests/workflows src/core/tests/memory
uv run pytest -m slow src/core/tests/workflows/test_e2e_runner.py
uv run ruff check . && uv run ruff format --check .
pre-commit run --all-files
cd src/frontend && npm run lint && npm run typecheck && npm test
cd src/frontend && npm run e2e
```

The fast suite needs Postgres (pgvector) and Redis on localhost (`DATABASE_URL`, `REDIS_URL`).

## Project structure (where the work goes)

```
src/core/dexterhouse/apps/projects/       models, services/, api/ (CR, context documents)
src/core/dexterhouse/apps/workflows/      ProcessRun iterations, runners/inputs.py, engine/
src/core/dexterhouse/apps/memory/         indexing of documents and CRs
src/core/dexterhouse/apps/workspaces/     workspace restore for a CR, delivery
src/builtin/agents/                       analyst/architect/PM prompts: iteration > 0 guidance
src/frontend/src/views/project/           Changes tab, context documents panel
src/core/tests/{projects,workflows,memory} tests mirror the app
docs/usage.md, docs/api.md               user docs updated in the same PR
```

## Code style

Follow the existing services: one module per concern, functions taking the model and the
`User`, state changes inside `transaction.atomic()`, an event emitted for every change,
errors from `dexterhouse.common.errors`.

```python
def queue_change_request(cr: ChangeRequest, user: User) -> ChangeRequest:
    """draft -> queued; starts at once when the project is already `completed`."""
    with transaction.atomic():
        project, _run = common.lock(cr.project_id)
        check_transition("change_request", cr.status, CRStatus.QUEUED, CR_ALLOWED)
        cr.status = CRStatus.QUEUED
        cr.save(update_fields=["status", "updated_at"])
        emit(project, "change_request.queued", {"number": cr.number}, actor=user_actor(user))
        if project.status == ProjectStatus.COMPLETED:
            start_next_change_request(project, user)
    return cr
```

Python 3.12, ruff, SPDX header on every file, Conventional Commits with no attribution
trailers, files kept short. Frontend: DexterOS glass components, i18n keys, no raw HTML from
agent or user Markdown.

## Testing strategy

- **Unit** (pytest, fast): state machines (CR, project `completed → running`), input
  selection per iteration, text extraction per format, limits and rejections.
- **API** (pytest + DRF client): permissions per role, validation errors, multipart upload.
- **Workflow** (fake runner): a completed project + one CR runs every phase again and emits
  `release.delivered` with `release-2`; a queued CR starts on completion.
- **Frontend** (vitest + Testing Library): Changes tab, upload panel; **e2e** (Playwright)
  one path: create CR on a completed demo project and see it running.
- Security: malformed PDF/DOCX, zip bomb DOCX, oversized file, wrong MIME, prompt text in a
  document does not change tool permissions.

## Boundaries

- **Always**: migrations in expand/contract style; events for every state change; update
  `docs/usage.md` and `docs/api.md`; tests next to each change; treat document text as
  untrusted data.
- **Ask first**: new dependencies (`pypdf`, `python-docx`); changing `ProcessRun` from
  one-to-one to one-to-many; changes to `src/schema` (process.yaml); runner protocol changes
  (workspace restore); a new ADR in `dev_docs/01_architecture/adr`.
- **Never**: delete or rewrite previous iterations' artifacts, events or tasks; let agents
  push; copy imported documents into the delivered repository without the user asking;
  touch `src/office` or `theme/tokens.json`.
