# REST API and WebSocket

Everything the web UI does goes through the public API: REST under `/api/v1` and a
WebSocket per project under `/ws`. The OpenAPI 3.1 document is generated from the code and
served by every installation at **`/api/v1/openapi.json`** (also kept as a CI artifact).
Import it into any OpenAPI client; this page covers what the document does not.

## Authentication

| Client | How |
|---|---|
| Browser (the SPA) | session cookie from `POST /api/v1/auth/login` (`{username, password}`); send the `csrftoken` cookie back as `X-CSRFToken` on writes (`GET /api/v1/auth/csrf` sets it) |
| Scripts, CI | `Authorization: Bearer dh_…` API token |

Create tokens on the server; the value is printed once and only its hash is stored:

```bash
docker compose exec web dexterhouse-manage tokens create --user admin --name ci --scopes projects:read,projects:write,events:read --days 90
docker compose exec web dexterhouse-manage tokens list
docker compose exec web dexterhouse-manage tokens revoke <token-id>
```

Scopes: `projects:read`, `projects:write`, `gates:decide`, `packages:manage`,
`events:read`. A token acts as its user in one organization: it needs the scope **and** the
user's role (`viewer` < `member` < `admin` < `owner`). With a session, pick the
organization with the `X-Organization: <slug>` header (default: the user's first).

```bash
curl -H "Authorization: Bearer $DH_TOKEN" http://localhost/api/v1/projects
```

## Resources

| Area | Endpoints |
|---|---|
| Projects | `GET/POST /projects`, `GET/PATCH/DELETE /projects/{id}`, `POST /projects/{id}/start\|pause\|resume\|retry`, `GET /projects/{id}/snapshot` |
| Artifacts, notes | `GET/POST /projects/{id}/artifacts`, `GET /artifacts/{id}`, `/versions`, `/diff`; `GET/POST /projects/{id}/notes`, `DELETE /notes/{id}` |
| Code (read-only) | `GET /projects/{id}/code/tree?ref=`, `/code/file?path=&ref=`, `/code/log?ref=&limit=`, `/code/location` |
| Workflow | `GET /projects/{id}/phases`, `GET /phases/{id}`, `POST /phases/{id}/skip`, `GET /projects/{id}/tasks`, `GET /tasks/{id}`, `POST /tasks/{id}/cancel` |
| Gates | `GET /gates?status=open` (inbox), `GET /projects/{id}/gates`, `GET /gates/{id}`, `POST /gates/{id}/decide` |
| Agents | `GET /projects/{id}/agents`, `/projects/{id}/turns`, `GET /agents/{id}`, `/agents/{id}/turns`, `GET /turns/{id}` |
| Events | `GET /projects/{id}/events`, `/events/summary`, `GET /events/{id}` |
| Costs | `GET /projects/{id}/costs`, `/llm-calls`, `/estimate`, `GET /estimate` (before creating), `GET/PUT /organization/budget`, `GET /organization/usage` |
| Packages | `GET/POST /packages`, `GET/DELETE /packages/{id}`, `POST /packages/{id}/enable\|disable`, `GET /packages/installs/{id}`, `POST /packages/installs/{id}/consent`, `POST /packages/validate`, `GET /marketplace/search\|status`, `GET /marketplace/packages/{name}` |
| Organization | `GET/PATCH /organization`, `GET /organization/members`, `GET /model-profiles`, `PUT /model-profiles/{profile}`, `GET /providers`, `GET /pricing` |
| Me, meta | `GET /auth/me`, `POST /auth/logout`, `GET /meta` (version, providers, processes, enabled features) |
| Notifications | `GET /notifications`, `/notifications/unread_count`, `POST /notifications/read`, `POST /notifications/{id}/read` |

Deciding a gate:

```bash
curl -X POST -H "Authorization: Bearer $DH_TOKEN" -H 'Content-Type: application/json' \
  -d '{"decision": "approve_with_comments", "comment": "Use PostgreSQL, not SQLite."}' \
  http://localhost/api/v1/gates/$GATE_ID/decide
```

Approvals take `approve`, `approve_with_comments` or `reject` (a comment is required except
for `approve`); questions take `{"answers": [{"question_id", "answer"}]}`; escalations take
`retry`, `accept` or `drop`. Deciding twice is a `409`.

The code endpoints read the project's workspace through the runner with read-only git
plumbing (no agent turn, no checkout). `ref` is a branch, a tag, `HEAD` (default) or a commit
id; files over 512 KB and binaries come back without `content`. Without a live workspace
they answer `503 workspace-unavailable`; `/code/location` still lists the delivered releases
(branch, pull request) from the `release.delivered` events.

## Conventions

- JSON, `snake_case`, ISO 8601 UTC dates, UUID ids; absent values are `null`, not omitted.
- **Pagination**: cursor based, `?cursor=…&limit=50` (max 200), answer
  `{"results": [...], "next": "<url>|null", "previous": "<url>|null"}`; newest first unless
  the endpoint says otherwise (phases, tasks and histories are oldest first; events take
  `order=desc`).
- **Secrets are write-only**: repository tokens and keys read back as `"***set***"`.

## Errors

Every error is an RFC 9457 `application/problem+json` document:

```json
{"type": "https://dexterhouse.dev/errors/invalid-transition", "title": "Invalid transition",
 "status": 409, "detail": "project cannot go from completed to running",
 "instance": "/api/v1/projects/…/start", "errors": []}
```

| Status | `type` suffix | When |
|---|---|---|
| 400 | `validation-error` | `errors[]` lists `{field, message}` |
| 401 / 403 | `not-authenticated`, `permission-denied` | missing credentials; role or scope too low |
| 404 | `not-found` | also for resources of other organizations |
| 402 | `budget-exceeded` | retrying with an exhausted budget |
| 409 | `invalid-transition`, `conflict` | state machine refusal, already decided |
| 422 | `idempotency-key-reused`, package schema errors | |
| 429 | `rate-limited` | with `Retry-After` in seconds |
| 503 | | a provider or the runner is unavailable |

## Idempotency

`POST /projects`, `POST /projects/{id}/artifacts`, `POST /projects/{id}/notes` and
`POST /packages` accept an `Idempotency-Key` header (1–255 characters). The first response
is kept for 24 hours per organization, client and key: retrying with the same key and body
returns it again with `Idempotent-Replayed: true` and creates nothing. The same key with a
different body is a `422`; a retry while the first request is still running is a `409`.
Errors are not kept, so a failed request can be retried with the same key. Gate decisions
need no key: deciding twice is refused.

## Rate limits

| Limit | Default | Variable |
|---|---|---|
| per API token, or per signed-in user | 600 requests/min | `API_RATE_CLIENT` |
| per IP, unauthenticated | 60 requests/min | `API_RATE_ANON` |
| sign-in attempts per IP | 10/min | `API_RATE_LOGIN` |
| WebSocket connections per project per browser session or token | 1 | `WS_CONNECTIONS_PER_PROJECT` |

Beyond a REST limit the answer is `429` with `Retry-After`. Counters live in Redis and are
shared by every web worker. The client IP is read behind `API_TRUSTED_PROXIES` reverse
proxies (1: nginx; 2 with Caddy in `compose.prod.yaml`). An empty rate disables that limit.

## WebSocket: `/ws/projects/{id}`

Authenticate with the session cookie or `?token=dh_…` (scope `events:read`). Messages are
JSON objects with a `type`.

Server → client:

| `type` | Content |
|---|---|
| `snapshot` | on connect and on request: `project`, `phases`, `tasks`, `gates_open`, `agents`, `workspace`, `budget`, `last_event_id` (same as `GET /projects/{id}/snapshot`) |
| `event` | `{"event": <envelope>}`: `id`, `type`, `schema_version`, `project_id`, `actor`, `correlation_id`, `created_at`, `payload` |
| `speaking` | streamed agent text, not persisted: `agent_id`, `turn_id`, `text`, `seq` |
| `heartbeat` | every 25 s: `server_time` |
| `error` | `code` (`forbidden`, `not_found`, `rate_limited`), `detail`; then the server closes |

Client → server: `{"type": "resync", "since_event_id": "…"}` resends the events after that
id (a fresh `snapshot` when it is unknown or more than 5 000 events behind),
`{"type": "subscribe_speaking", "enabled": false}`, `{"type": "ping"}`. At most 20 client
messages per 10 seconds.

Close codes: `4401` not authenticated, `4403` forbidden, `4404` unknown project, `4429`
too many connections or messages. Events of a project arrive in order; a client that
reconnects and sends `resync` with the last id it saw misses nothing. Unknown event types
must be ignored; the payload of each type is stable within its `schema_version`.

There is no organization-wide WebSocket yet: the project list and the inbox poll
`GET /projects`, `GET /gates?status=open` and `GET /notifications/unread_count`.

## Metrics and health

Not under `/api`: `GET /health/live`, `GET /health/ready` (database and Redis) and
Prometheus `GET /metrics` on `web:8000`, reachable only inside the Compose network
([operations.md](operations.md)).
