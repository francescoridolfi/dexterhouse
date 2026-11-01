# Operating DexterHouse

Install, upgrade, backup and restore are in [install.md](install.md). This page covers what
to watch once it runs.

## Health

`docker compose ps` shows the healthchecks: `web` (`/health/ready`: database and Redis),
`worker` (`celery inspect ping`), `beat` (its pid), `runner` (`dexterhouse-runner health`),
`frontend`, `proxy`, `postgres`, `redis`. `secrets-init` and `migrate` run once and exit 0.

## Metrics

Prometheus text format on `web:8000/metrics` and `runner:9100/metrics`, inside the Compose
network only (nginx does not expose them). The values are computed from Postgres and Redis
at scrape time, so every web replica reports the same numbers.

| Series | Meaning |
|---|---|
| `dh_llm_calls_total{provider,model,status}`, `dh_llm_tokens_total{kind}`, `dh_llm_cost_eur_total`, `dh_llm_latency_seconds` | LLM usage, cost and latency |
| `dh_agent_turns_total{status}` | agent turns (`rate(...[5m])*60` = turns per minute) |
| `dh_projects{status}`, `dh_gates_open{type}` | projects by state, gates waiting for people |
| `dh_queue_length{queue}` | Celery queues `agents`, `default`, `core-callbacks`, `runner` |
| `dh_workspaces_active`, `dh_runner_up`, `dh_runner_heartbeat_age_seconds`, `dh_runner_exec_total`, `dh_runner_errors_total`, `dh_runner_egress_denied_total` | runner and sandboxes, from the runner heartbeats |
| `dh_gateway_breaker_open{provider}` | 1 while a provider's circuit breaker is open |
| `dh_security_violations_recent` | `security.violation` events in the last 10 minutes |
| `runner_*` on `runner:9100` | the runner's own counters (exec durations, errors by code, denied egress) |

`docker compose -f compose.yaml -f compose.prod.yaml --profile monitoring up -d` adds
Prometheus (`docker/prometheus/`, UI on `127.0.0.1:9090`) with the alert rules below. Point
an Alertmanager or Grafana at it to be notified; neither is bundled. Host metrics (disk,
CPU) come from your usual node exporter or cAdvisor.

## Logs

Every core service logs one JSON object per line on stdout: `ts`, `level`, `service`,
`logger`, `event`, `trace_id`, `project_id`, `agent_turn_id`, `request_id` (plus
`task_id`/`task_name` in Celery). Prompts and model output are never logged at `INFO`;
tokens, keys and passwords are redacted. `LOG_FORMAT=console` is easier to read locally,
`LOG_LEVEL=DEBUG` for a short investigation only. `compose.prod.yaml` rotates the Docker
logs (`json-file`, 5 × 50 MB per container).

```bash
docker compose logs -f worker | grep '"project_id": "01a1…"'
```

Tracing: set `OTEL_EXPORTER_OTLP_ENDPOINT` to an OTLP/HTTP collector to export the spans
`http.request`, `agent.turn` and `llm.call`; log lines carry the same `trace_id`.

## Retention

| Data | Kept | How |
|---|---|---|
| events | `EVENTS_RETENTION_MONTHS` (12) | monthly partitions; `beat` creates the next ones and drops expired ones every night at 03:00 |
| LLM calls | 6 months in detail | then aggregated per day (`llm_usage_daily`) on the 1st of the month |
| artifacts, decisions, costs of a project | until the project is deleted | |
| workspaces | while the project runs | destroyed when the project is archived, or 24 h (`WORKSPACE_IDLE_DESTROY_H`) after it completes |
| Redis streams | the latest 10 000 events per project | the database is the source of truth |

Events are append-only: the database refuses updates and deletes on them except for the
publication flag.

## Alerts and runbooks

The rules are in `docker/prometheus/alerts.yml`. Three more checks have no metric in the
stack and belong to your host monitoring: free disk on the Docker data root (critical below
10 %), the age of the last backup (warning after 26 hours), and the TLS certificate (Caddy
renews it 30 days ahead; warn below 14 days).

### RunnerDown

No runner heartbeat for 60 s. Workspaces cannot run tools; agent turns that need them fail
and are retried, then escalate.

1. `docker compose ps runner` and `docker compose logs --tail 100 runner`.
2. The runner needs the Docker socket and Redis: `docker info` on the host, `docker compose
   ps redis`.
3. `docker compose restart runner`. Core and runner must run the same `DH_VERSION`; a
   mismatch is logged at start.
4. When it is back, decide the open `turn_failed` escalations with *Retry*.

### QueueBacklog

The `agents` or `runner` queue has held more than 50 tasks for 10 minutes.

1. Check the workers are alive: `docker compose ps worker runner`.
2. Many projects at once: raise `WORKER_CONCURRENCY` (agents) or `RUNNER_CONCURRENCY`, or
   run more workers (`docker compose up -d --scale worker=2`).
3. One project looping: find it in `GET /api/v1/projects?status=running` and the Log tab;
   pause it.

### ProviderBreakerOpen

A provider failed 5 times in a minute and the gateway stopped calling it for 2 minutes,
repeatedly for 5 minutes.

1. `docker compose logs worker | grep llm.` for the error (auth, quota, outage).
2. Test it: `docker compose exec web dexterhouse-manage gateway call "ping" --provider <name> --model <model>`.
3. Invalid key: fix `.env`, `docker compose up -d`. Outage: wait, or map the profiles to
   another provider in *Settings → Model profiles* (`allow_downgrade` lets `strong` fall
   back to `balanced`).

### SecurityViolations

More than 10 `security.violation` events in 10 minutes: agents keep calling tools they are
not allowed to, or arguments their policy refuses. The third violation in a turn blocks it
and opens a `security` escalation.

1. Find the project and the agent: `GET /api/v1/gates?status=open&type=escalation` or the
   Inbox; the events carry `agent_id`, `tool` and `kind`.
2. A package that misbehaves (often a third-party agent whose prompt asks for tools it does
   not declare, or prompt injection from a fetched page): disable it with `dexterhouse pkg
   disable <name>` and *Drop* the task.
3. Report suspicious packages to the registry maintainers ([security.md](security.md)).

### Disk full

Workspaces are capped by `WORKSPACE_DISK` each; the database grows with events.

1. `docker system df -v`; workspace volumes are `dh-ws-*`.
2. Archive finished projects (their workspaces are destroyed by the next cleanup) or lower
   `WORKSPACE_IDLE_DESTROY_H`.
3. Lower `EVENTS_RETENTION_MONTHS` if the database is the problem; old partitions are
   dropped the next night.

### Backup missing

Run the backup of [install.md](install.md#backup-and-restore) from cron and alert on the age
of the newest file. Test a restore on another machine at every upgrade.

## Workspace images

The workspace images (`dexterhouse-workspace:python`, `:node`, `:full`) are rebuilt from
updated base images every Monday and scanned with Trivy before they are pushed. New
workspaces use the new digest; running ones keep theirs. To refresh by hand:
`docker pull ghcr.io/francescoridolfi/dexterhouse-workspace:python`.
