# Security model

DexterHouse runs code written by language models, guided by prompts that may come from
third-party packages or fetched web pages. It treats that code and those prompts as
hostile. This page says what is isolated, what agents can and cannot do, and what you have
to do as the operator. To report a vulnerability see [SECURITY.md](../SECURITY.md).

## The sandbox

```
 web, worker, beat ──(Celery, internal network)── runner ──(Docker socket)── workspace containers
        │                                            │                         │
   Postgres, Redis                           pushes on delivery         dh_sandbox_<id> network
                                                                               │
                                                                    proxy (allow-listed egress)
```

- **Only the runner has the Docker socket.** The core and the agents never do; they ask the
  runner over a dedicated queue ([ADR-0006](adr/0006-separate-runner.md)).
- **One container per project workspace**, created by the runner: user `1000:1000`, all
  capabilities dropped, `no-new-privileges`, read-only root filesystem, `pids` (256), CPU
  (`WORKSPACE_CPUS`), memory (`WORKSPACE_MEM`) and disk (`WORKSPACE_DISK`) limits, no
  `sudo`, no Docker client, no setuid binaries.
- **Network**: each workspace and its service sidecars (a database for the project's tests)
  get their own internal network `dh_sandbox_<id>`, with no route to Postgres, Redis, the
  core or other workspaces. The only exit is the Squid proxy, which allows HTTPS to the
  hosts in `WORKSPACE_EGRESS_ALLOWLIST` (package registries and GitHub by default) and
  refuses the rest. DNS does not resolve outside names, so DNS exfiltration fails too.
- **Images**: only `WORKSPACE_IMAGE_ALLOWLIST` images run, pinned by digest at creation. They
  are rebuilt weekly from updated bases and scanned.
- **The runner holds no secrets**: no database access, no encryption key. For a delivery
  push the core issues a one-time grant valid for 60 seconds; the runner redeems it and hands
  the token to git through `GIT_ASKPASS` for that push only. The token never enters a
  workspace ([ADR-0016](adr/0016-runner-without-secrets.md)).

Optional stronger isolation (gVisor, `RUNNER_RUNTIME=runsc`) is planned for 1.x.

## What agents can do

- Call the tools their package declares, and only those: every call goes through the core's
  tool gateway, which checks the agent's allowed tools and the argument policies (for
  example the Tester may only write test files) before the tool server sees it. Refusals
  are `security.violation` events; the third one in a turn blocks the turn and opens an
  escalation for a human.
- Tools with `risk: high` permissions are refused and escalated until an admin allows them
  for the phase.
- Write and run code **inside their workspace** only; commit to the workspace's local
  repository. `detect-secrets` runs before every commit and refuses commits with secrets.
- Read the project's artifacts, notes and memory; ask you questions in `supervised` mode.

## What agents cannot do

- Push, merge or open pull requests: no agent has a push tool. Delivery is a system action
  after you approve the release, never a force-push ([delivery.md](delivery.md)).
- Reach the host, the Docker socket, the database, other projects or arbitrary hosts.
- See API keys, repository tokens or other secrets.
- Install packages in `supervised` mode; in `autonomous` mode only verified, low-risk
  packages from the registry, and never anything with high-risk permissions.
- Override the core's system prompt: package prompts come after it, content from tools that
  read outside sources (marketplace README files, web pages) is wrapped as untrusted, and
  prompts with instructions to ignore rules are rejected at validation.

## Packages

Packages are declarative (YAML, Markdown, images): no Python from the marketplace runs in
the core. Tool packages start MCP servers with a pinned `uvx`/`npx`/`python`/`node`
launcher, in the worker or inside the workspace, with the permissions and risks they
declare. Git installs are verified against the registry index (same repository, tag and
sha256); a package whose hash differs is refused. Installing `risk: high` permissions needs
explicit consent. Details: [packages.md](packages.md), [authors.md](authors.md).

## Secrets

- Generated on first start into the `dh_secrets` volume (Django key, Fernet key, runner key,
  database password), readable only by the services that need them; never in `.env`.
- Provider keys come from the environment; repository tokens are stored encrypted with the
  Fernet key and are write-only in the API (`"***set***"`). Logs redact tokens, keys and
  passwords.

## The web application

Session cookies are `HttpOnly`, `Secure` and CSRF-protected; API tokens have scopes and act
within one organization and the user's role. Every query is filtered by organization: a
resource of another organization answers `404`. The UI is served with a strict Content
Security Policy (no inline scripts) and renders agent output as text. Rate limits protect
sign-in, the API and the WebSocket ([api.md](api.md#rate-limits)). Gate decisions record
who and when, and the event log is append-only in the database.

## Operator checklist

- Run behind TLS (`compose.prod.yaml`) and keep `COOKIE_SECURE=true`.
- Keep `WORKSPACE_EGRESS_ALLOWLIST` as short as your stacks allow.
- Back up the database **and** the `dh_secrets` volume, encrypted, off the host.
- Give delivery tokens the smallest scope: one repository, contents and pull requests.
- Use `data_residency: local` for projects whose code must not reach a cloud model.
- Upgrade promptly: security fixes ship as patch releases; images are rebuilt weekly.
- Watch the `SecurityViolations` alert ([operations.md](operations.md#securityviolations)).
- The runner is root-equivalent on the host (it has the Docker socket): do not run other
  workloads you care about on the same Docker daemon, or use a dedicated VM.

## Security tests

The threat model (T1–T20) is checked by tests that run in CI on every pull request; a red
test blocks a release.

| Test | What it proves | Where |
|---|---|---|
| ST-01 | no Docker socket or client in a workspace | `security` job (real runner, real workspace) |
| ST-02 | no route to Postgres, Redis, web or unlisted hosts; denied egress counted | `security` |
| ST-03 | uid 1000, no sudo, no capabilities, no writes outside the volume | `security` |
| ST-04 | tools with a launcher outside the allow-list are rejected | `security` |
| ST-05 | `risk: high` packages wait for consent | `test` (packages) |
| ST-06 | a prompt-injected README does not give an agent new tools | `test` (Recruiter, marketplace) |
| ST-07 | forbidden prompt patterns fail validation | `security` |
| ST-08 | three refused calls block the turn and escalate, nothing reaches the runner | `security`, `test` |
| ST-09 | commits with secrets are refused | `security` |
| ST-10 | the delivery token never appears in the workspace | `security` |
| ST-11 | the budget stops the project and escalates | `test` (budget) |
| ST-12 | other organizations' resources answer 404 | `test` (API) |
| ST-13 | roles and scopes are enforced | `test` (API) |
| ST-14 | `data_residency: local` refuses cloud providers before the call | `test` (gateway) |
| ST-15 | protected branches refuse delivery; never `--force` | `security` |
| ST-16 | secret grants are single use, authenticated and expire | `security` |
| ST-17 | secrets are write-only in responses and redacted in logs | `test` |
| ST-18 | fork bombs and disk filling stay inside the limits | `security` |
| ST-19 | no DNS resolution outside the sandbox | `security` |
| ST-20 | agent output is not executed in the UI | manual per release (see below) |
| ST-21 | one WebSocket per project per client (4429), resync falls back to a snapshot | `test` (events) |
| ST-22 | a package whose hash differs from the index is refused | `test` (installer) |
| ST-23 | events cannot be updated or deleted | `test` (events) |
| ST-24 | images outside the allow-list are never pulled | `security` |
| ST-25 | sidecars of one workspace are unreachable from another | `security` |

Run them: `uv run pytest -m security` (needs Docker and the `workspace:python` image) and
`uv run pytest -m "not slow and not security"`.

Manual checks at every release: ST-20 (render an artifact containing `<script>` and
`<img onerror>` in the 2D view and confirm nothing runs: artifacts are shown as text and the
CSP forbids inline scripts; no automated browser test yet), the Trivy report of the release
images, the permission diff of the built-in packages, a backup restore on a clean machine,
and an OWASP ZAP baseline scan of the UI.

## Accepted risks (1.0)

A compromised host or Docker daemon; a container escape through an unpatched kernel or
`runc` vulnerability (mitigated by the weekly image rebuilds and, in 1.x, gVisor); a
malicious registry maintainer (two-person review for `verified` is planned); Celery
messages on the internal Redis are not signed (an attacker needs a container on the internal
network first; signing is planned for 1.x).
