# Spec: context-documents

Shared commands, style and boundaries: [README.md](README.md).

## Objective

Let a user import external documents (technical analyses, domain notes, API descriptions,
existing specs) into a project so the pipeline and the agents work from them, not only from
the brief. Users: `member` and above, on the new-project form and on the project page.

## Design

- **Storage**: each document is an `Artifact` of the new kind `context`: `content` holds the
  extracted text, `data` holds `{filename, mime, size, sha256, pages, active, change_request}`.
  Versioning, full-text search and memory indexing already exist for artifacts. The original
  file is stored under `MEDIA_ROOT/context/<project_id>/<sha256>` for download only.
- **Extraction**: text formats read as UTF-8 (BOM and Latin-1 fallback); PDF with `pypdf`,
  DOCX with `python-docx` (headings kept as Markdown `#`). Runs in a Celery task with a 60 s
  timeout; the document is `processing` until done, `failed` with a reason otherwise. Scanned
  PDFs without a text layer fail with `no_text_layer` (no OCR in this version).
- **Limits** (settings, with defaults): 10 MB per file, 20 active documents per project,
  200 000 extracted characters per document (longer text is cut and flagged
  `truncated`). The type is checked from the content, not only the extension.
- **Memory**: an active document is chunked and embedded like any artifact; `memory.search`
  returns it with `kind: context`. Without an embedder agents still get it as input.
- **Agent inputs**: `context` is added to `DEFAULT_INPUTS` for `analyst`, `architect` and
  `project_manager`. Each document enters the turn whole up to 8 000 characters; longer ones
  enter as title + first 2 000 characters + a line telling the agent to use `memory.search`.
  Other roles reach documents through `memory.search` only. The context manifest of the turn
  lists which documents were read.
- **Lifecycle**: documents can be added or deactivated in any state except `archived`. Added
  mid-run, they reach the next turns (like notes). Deactivating sets `active: false` (new
  artifact version) and removes its memory chunks; nothing is hard-deleted.
- **Untrusted text**: document content is wrapped as data in the prompt (same treatment as
  the brief), never as instructions; it cannot widen tools, risk levels or budgets.

## API (REST v1)

| Method | Path | Notes |
|---|---|---|
| `POST` | `/projects/{id}/context` | multipart `file`, optional `title`, `change_request`; 202 with the document in `processing` |
| `GET` | `/projects/{id}/context` | active documents; `?all=1` includes deactivated |
| `GET` | `/context/{doc_id}` | metadata + extracted text; `/download` streams the original |
| `DELETE` | `/context/{doc_id}` | deactivates (admin, or the member who uploaded it) |

Events: `context.added`, `context.processed`, `context.failed`, `context.deactivated`.

## UI

- New project form: a drop zone under the brief ("Context documents", optional).
- Project page, Overview: a **Context** panel listing documents (name, size, status, who,
  when), upload button, preview of the extracted text, deactivate.

## Acceptance criteria

1. A member uploads `analysis.pdf` (3 pages) to a draft project; within 60 s it is `processed`
   and its text is visible in the panel.
2. The analyst's first turn lists that document in its `context_manifest` and its inputs.
3. A 25 000-character document reaches the architect truncated with the `memory.search`
   hint, and `memory.search` finds a sentence from its last page.
4. A 12 MB file, a 21st document, an `.exe` renamed `.pdf` and a DOCX zip bomb are refused
   with `validation_failed` and a field-level reason; nothing is stored.
5. A `viewer` cannot upload or deactivate (403).
6. Deactivating removes the document from later turns and from `memory.search` results.
7. Uploading while the project is `running` emits `context.added`; the next turn reads it.
8. An archived project refuses uploads (`invalid_transition`).

## Tests

`src/core/tests/projects/test_context_documents.py` (service, limits, lifecycle),
`test_context_api.py` (roles, multipart), `src/core/tests/memory/test_context_index.py`,
`src/core/tests/workflows/test_inputs_context.py` (truncation, roles), fixtures in
`src/core/tests/fixtures/context/` (tiny PDF, DOCX, scanned PDF, zip bomb).
Frontend: `views/project/__tests__/ContextPanel.test.tsx`.

## Open questions

- Q1. Keep originals on the `web` volume or add an object storage setting now? (Proposal:
  volume now, setting later.)
- Q2. Should the user be able to mark a document *always in full* for every role (pinned)?
  Proposal: not in v1.
