# Command line

The core image ships three command-line tools. They run **inside** the stack, against its
database, so call them through `docker compose exec web …` (or `exec worker`). A remote CLI
that only uses the public API is planned for 1.x; until then scripts use the
[REST API](api.md) with a token.

## `dexterhouse pkg`: packages

```bash
docker compose exec web dexterhouse pkg list [--org <slug>]
docker compose exec web dexterhouse pkg install security-reviewer --version 1.2.0 [--org <slug>]
docker compose exec web dexterhouse pkg install git+https://github.com/janedoe/dh-security-reviewer@v1.2.0
docker compose exec web dexterhouse pkg disable security-reviewer
docker compose exec web dexterhouse pkg enable security-reviewer
docker compose exec web dexterhouse pkg remove security-reviewer
```

Without `--org` the package is global (every organization sees it); global packages are
managed only from here, not from the API. `risk: high` permissions are listed and need
`--confirm-permissions`. `remove` is refused while an active project uses the package.

For package authors ([authors.md](authors.md)), from a checkout of this repository
(`uv sync`) or inside the container:

```bash
uv run dexterhouse pkg init my-reviewer --kind agent   # also: tool, process
uv run dexterhouse pkg validate ./my-reviewer
```

## `dexterhouse-manage`: administration

| Command | What it does |
|---|---|
| `bootstrap_owner --username admin` | create the default organization and its owner (password from `DH_OWNER_PASSWORD`; `--reset-password` to change it) |
| `tokens create --user U --name N --scopes a,b [--org slug] [--days 90]` | create an API token; prints it once |
| `tokens list [--org slug]`, `tokens revoke <id>` | list or delete tokens |
| `events tail <project_id> [--from-start] [--json]` | follow a project's live event stream |
| `events emit <project_id> <type> --payload '{…}'` | emit a system event (debugging) |
| `gateway call "prompt" [--profile balanced] [--provider P --model M]` | one LLM call through the gateway, to test a provider |
| `costs refresh` | recompute project and organization spend from the recorded calls |
| `costs rollup` | aggregate old LLM calls into daily usage (also monthly by `beat`) |
| `memory reindex --project <id>` or `--all` | re-embed the project memory after changing the `embed` model (`--dry-run` first) |
| `packages sync-builtin` | install new or changed built-in packages (run by `migrate` at every start) |
| `packages check-compat` | disable packages whose `compat.core` excludes this core |
| `migrate`, `createsuperuser`, … | the usual Django commands |

Examples:

```bash
docker compose exec web dexterhouse-manage events tail 01a19923-… --from-start
docker compose exec web dexterhouse-manage gateway call "Say hi" --profile fast
```

## `dexterhouse-schema`: package checks

The same validator the installer and the registry CI use, published as the
`dexterhouse-schema` Python package:

| Command | What it does |
|---|---|
| `validate <dir or file>` | schema, file layout and prompt checks of a package |
| `scan-prompts <dir>` | forbidden instructions in prompts and skills |
| `hash <git-dir> --ref v1.0.0` | sha256 of `git archive --format=tar <ref>`, the value the registry stores |
| `check-entry packages/<name>.json <checkout>` | a registry entry against the package checkout |
| `check-registry-update <old> <new>` | the rules for changing a registry entry |
| `export-jsonschema <dir>` | the JSON Schemas of every file kind, for editors |

```bash
uvx dexterhouse-schema validate ./my-reviewer   # once published on PyPI; before, see authors.md
```

## `dexterhouse-runner`

Inside the runner container: `dexterhouse-runner health` (the healthcheck) and
`dexterhouse-runner version`. `worker` is the service command.
