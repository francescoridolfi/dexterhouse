# Installing DexterHouse

DexterHouse runs as a Docker Compose stack: the core (`web`, `worker`, `beat`), the
`runner` (the only service with the Docker socket), an egress `proxy` for the sandboxes,
the `frontend` (nginx and the web UI), PostgreSQL with pgvector, and Redis.

## Requirements

- Docker Engine 25 or newer with Compose v2.24 or newer (Docker Desktop on macOS and
  Windows is fine). The runner mounts `/var/run/docker.sock`.
- 4 vCPU and 8 GB RAM recommended; about 10 GB of disk for the images, plus the projects'
  workspaces (5 GB quota each by default).
- An LLM: an Anthropic or OpenAI API key, an OpenAI-compatible endpoint, or a local
  [Ollama](https://ollama.com). Without one, the demo mode below runs everything on a fake
  provider.
- A browser with WebGL 2 for the 3D office; the 2D dashboard works everywhere.

## Quickstart

```bash
git clone https://github.com/francescoridolfi/dexterhouse.git && cd dexterhouse
cp .env.example .env
docker compose up -d --wait
```

The first start generates the secrets (Django key, Fernet key, runner key, Postgres
password) into the `dh_secrets` volume, runs the migrations and installs the built-in
agents, tools and processes. `--wait` returns when every service is healthy; check with
`docker compose ps`.

`docker compose up` pulls the images of `DH_VERSION` from `ghcr.io/francescoridolfi` and
builds them from source when they are not published (any version before `1.0.0`, or a
checkout with local changes). The **workspace images** that run the agents' code are pulled
by the runner the first time a project needs them; to build them locally instead:

```bash
docker compose --profile images build
```

Create the first owner (the organization `default` is created with it):

```bash
printf 'Owner password: ' && read -rs DH_OWNER_PASSWORD && export DH_OWNER_PASSWORD
docker compose exec -e DH_OWNER_PASSWORD web dexterhouse-manage bootstrap_owner --username admin
```

Open <http://localhost> and sign in.

## Connect a model

Agents ask for a profile (`strong`, `balanced`, `fast`, `embed`); the defaults use
Anthropic. Put the keys in `.env` and recreate the services that read them:

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...        # optional: also the fallback embedder
```

```bash
docker compose up -d
```

To use other providers or models, map the profiles in *Settings → Model profiles*. For
Ollama on the same machine keep `OLLAMA_BASE_URL=http://host.docker.internal:11434` (the
worker resolves it on Linux too) and pull the models first, e.g. `ollama pull
mxbai-embed-large`. Provider details: [providers/README.md](providers/README.md).

**Demo without an LLM**: set `GATEWAY_FAKE_RESPONDER=dexterhouse.apps.agents.demo.respond`
in `.env`, run `docker compose up -d`, then map every profile to provider `fake` (model
`fake-model`; `embed`: `hash-1024`). A project then runs through every phase in a few
minutes with canned artifacts.

## Ports and addresses

| Port | Service | Notes |
|---|---|---|
| `HTTP_PORT` (80) | frontend | UI, `/api/v1`, `/ws`; the only published port in production |
| 127.0.0.1:5432, 127.0.0.1:6379 | postgres, redis | development only (`compose.override.yaml`) |
| 127.0.0.1:8025 | Mailpit | development only: catches the gate notification emails |

`docker compose up` also loads `compose.override.yaml`, meant for development. On a server
use the production overlay below, which does not.

If you change `HTTP_PORT` or reach the UI by another name, list every origin browsers use
in `CSRF_TRUSTED_ORIGINS` (with the port, e.g. `http://localhost:8080`) and the host names in
`ALLOWED_HOSTS`, otherwise sign-in fails with a CSRF error. Session cookies are `Secure`:
browsers accept them over plain HTTP only on `localhost`. For a plain-HTTP address on a
trusted network set `COOKIE_SECURE=false`; anywhere else use TLS.

## Production: TLS with Caddy

`compose.prod.yaml` puts [Caddy](https://caddyserver.com) in front of the frontend with an
automatic Let's Encrypt certificate, rotates the logs, runs the core containers with a
read-only root filesystem and does not publish Postgres or Redis.

1. Point a DNS name at the host; open ports 80 and 443.
2. In `.env`:

   ```bash
   CADDY_DOMAIN=dexterhouse.example.com
   ALLOWED_HOSTS=dexterhouse.example.com,web
   CSRF_TRUSTED_ORIGINS=https://dexterhouse.example.com
   PUBLIC_URL=https://dexterhouse.example.com
   WEB_WORKERS=4
   ```

3. Start it:

   ```bash
   docker compose -f compose.yaml -f compose.prod.yaml up -d --wait
   ```

Add `--profile monitoring` for Prometheus with the alert rules ([operations.md](operations.md)).
Keep using both `-f` files for every later command (`exec`, `logs`, `pull`), or set
`COMPOSE_FILE=compose.yaml:compose.prod.yaml` in the shell.

Gate notifications by email need SMTP settings: `NOTIFICATIONS_EMAIL=true`, `EMAIL_HOST`,
`EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_USE_TLS`, and the password in a file named by
`EMAIL_HOST_PASSWORD_FILE` (mounted into `web` and `worker`), never in `.env`.

## Upgrade and rollback

1. Back up (next section) and read the release notes in `CHANGELOG.md`.
2. Set the new version and pull:

   ```bash
   sed -i.bak 's/^DH_VERSION=.*/DH_VERSION=1.1.0/' .env
   docker compose pull
   docker compose up -d --wait
   ```

   The `migrate` service applies the migrations and re-syncs the built-in packages before
   `web`, `worker` and `beat` start. Running agent turns resume; existing workspaces keep
   their image. Core and runner must run the same `DH_VERSION`.

3. Rollback: set the previous `DH_VERSION` and `docker compose up -d`. Migrations are
   additive within a major version, so the previous minor still runs; when a release says a
   migration is not reversible, roll back by restoring the backup of step 1.

## Backup and restore

What to keep: the Postgres database, `.env`, and the `dh_secrets` volume (without the
Fernet key the stored repository tokens and API keys cannot be decrypted). Workspaces are
disposable; installed packages can be reinstalled from the registry.

```bash
mkdir -p backups
docker compose exec -T postgres pg_dump -Fc -U dexterhouse dexterhouse > backups/db-$(date +%F).dump
docker run --rm -v dexterhouse_dh_secrets:/s:ro -v "$PWD/backups:/b" alpine tar czf /b/secrets-$(date +%F).tgz -C /s .
```

Store both outside the host, encrypted. Restore into an empty database:

```bash
docker compose stop web worker beat runner
docker compose exec -T postgres dropdb -U dexterhouse --force dexterhouse
docker compose exec -T postgres createdb -U dexterhouse dexterhouse
docker compose exec -T postgres pg_restore -U dexterhouse -d dexterhouse --no-owner < backups/db-2027-05-16.dump
docker compose up -d --wait
```

Events not yet published to Redis are republished by `beat` within a minute. The volume
names start with the Compose project name (`dexterhouse_` by default).

## Uninstall

`docker compose down` stops the stack and keeps the data; `docker compose down -v` also
deletes the volumes (database, secrets, packages). Workspace containers and their
`dh-ws-*` volumes are created by the runner, not by Compose: they are destroyed when a
project is archived or `WORKSPACE_IDLE_DESTROY_H` hours (24) after it completes. Remove
leftovers with `docker ps -a --filter label=dexterhouse.project`.

## Troubleshooting

| Symptom | Check |
|---|---|
| a service is not healthy | `docker compose logs <service>`; `migrate` must have exited 0 |
| sign-in fails with 403 | `CSRF_TRUSTED_ORIGINS`, `ALLOWED_HOSTS`, `COOKIE_SECURE` (section *Ports*) |
| a project waits on `workspace_not_ready` | the workspace image is missing: `docker compose --profile images build` or check the runner logs |
| turns fail with provider errors | the key in `.env`, then `docker compose up -d`; *Settings → Model profiles* |
| `429 rate-limited` | `API_RATE_*` in `.env` ([api.md](api.md#rate-limits)) |
