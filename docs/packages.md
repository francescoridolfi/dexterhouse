# Packages

Agents, tools (MCP servers) and processes are **declarative packages**: a `dexterhouse.yaml`
manifest plus `agent.yaml`, `tool.yaml` or `process.yaml`, prompts, skills and assets. No
Python code is installed. The built-in team is installed the same way as everything else,
at every start, by the `migrate` service (`manage.py packages sync-builtin`).

## Where packages come from

| Source | Example | Notes |
|---|---|---|
| Registry name | `security-reviewer` (`--version 1.2.0`) | resolved through `REGISTRY_INDEX_URL` |
| Git tag | `git+https://github.com/janedoe/dh-security-reviewer@v1.2.0` | shallow clone of the tag |
| Local folder | `./my-agent` | development only (`PACKAGES_ALLOW_LOCAL=true`) |

Every install is checked before anything is enabled:

- **sha256**: when the package is listed in the registry index, the `git archive` of the tag
  must match the hash in the index, otherwise it is rejected. If the index cannot be reached
  and no saved copy exists, git installs are refused.
- **Schema**: the package must pass `dexterhouse pkg validate` (the registry CI runs the same
  checks).
- **Compatibility**: `compat.core` must include the running core version. After a core upgrade,
  packages that no longer fit are disabled with a warning; running projects keep them.
- **Permissions**: a tool with `risk: high` permissions (or an agent that requires one) waits
  for an admin to accept the listed permissions.

Installed files live in `PACKAGES_DIR` (default `/data/packages`, the `packages` volume).
During planning the [Recruiter](recruiter.md) searches the same registry and proposes
specialist agents at the `approve_plan` gate.

## Command line

`validate` and `init` work on a folder. The other commands run where the core runs
(`docker compose exec web dexterhouse pkg …`); without `--org` they manage packages shared by
every organization.

```bash
dexterhouse pkg init security-reviewer --kind agent
dexterhouse pkg validate ./security-reviewer
dexterhouse pkg install ./security-reviewer --org acme
dexterhouse pkg install git+https://github.com/acme/dh-git-tools@v0.3.0 --confirm-permissions
dexterhouse pkg list --org acme --kind agent
dexterhouse pkg disable security-reviewer --org acme
dexterhouse pkg remove security-reviewer --org acme
```

Exit codes: `1` invalid or rejected, `2` usage error, `3` high-risk permissions not accepted.

## API

Admins install with `POST /api/v1/packages` (`{"source": "git+https://…@v1.2.0"}` or
`{"marketplace": "security-reviewer", "version": "1.2.0"}`, optional
`"confirm_permissions": ["git.push"]`) and follow `GET /api/v1/packages/installs/{id}`;
`POST …/consent` with `{"accept": true}` grants the high-risk permissions. Disabling or
upgrading a package never changes a running project: its agents stay on the version they
were hired with until the project ends. A package used by an active project cannot be
removed.

## Install telemetry (opt-in)

Off by default. When an organization owner sets `"telemetry": true` in the organization
settings (`PATCH /api/v1/organization` with `{"settings": {"telemetry": true}}`) and
`MARKETPLACE_URL` is set, each successful install of a registry package by that
organization sends `{package, version, core_version, instance_hash}` to
`{MARKETPLACE_URL}/api/v1/installs`. Nothing else is sent: no IP address is stored by the
marketplace, no user or project data leaves the core. `instance_hash` is
`sha256(installation id + "YYYY-MM")`; the installation id is random, kept in
`PACKAGES_DIR/.instance/installation_id` and never sent, so the hash changes every month
and installs cannot be linked across months. Local, built-in and global (CLI without
`--org`) installs are never reported; a failed report is only logged.

To publish your own packages, see [authors.md](authors.md).
