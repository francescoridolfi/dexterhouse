# Contributing to DexterHouse

Thank you for considering a contribution. This guide covers setup, conventions and what "done" means here. By contributing you agree to the [Code of Conduct](CODE_OF_CONDUCT.md) and, for code or documentation changes, to the [Contributor License Agreement](CLA.md) (the CLA bot will ask you once).

## Before you start
- Check existing issues and discussions; open an issue for anything beyond a small fix so we can agree on the approach.
- Architecture changes need an **ADR** (see below) before code.
- Agent, tool and process packages do **not** belong in this repository: publish them to the [registry](https://github.com/francescoridolfi/dexterhouse-registry).

## Development setup
```bash
git clone https://github.com/francescoridolfi/dexterhouse.git && cd dexterhouse
cp .env.example .env
uv sync --all-groups
uv tool install pre-commit && pre-commit install --hook-type pre-commit --hook-type commit-msg
docker compose up -d postgres redis   # exposed on 127.0.0.1 by compose.override.yaml
export DATABASE_URL=postgres://dexterhouse:$(docker compose exec -T postgres cat /run/dh-secrets/pg_password)@localhost:5432/dexterhouse
export REDIS_URL=redis://localhost:6379/0
uv run manage.py migrate && uv run manage.py createsuperuser
cd src/frontend && npm ci && cd -
```
Run: `uv run manage.py runserver`, `uv run celery -A dexterhouse worker -Q agents,default,core-callbacks -l info`, `cd src/frontend && npm run dev`. Useful: `uv run manage.py events tail <project_id>`, `uv run manage.py gateway call "hi"` (fake provider), `uv run dexterhouse-schema validate <package_dir>`. The runner arrives in a later epic.

Tests: `uv run pytest` (unit + integration, no real LLM calls: the `fake` provider is used), `npm test` in `src/frontend`, `uv run pytest -m security` with the runner up.

## Conventions
- **Python 3.12**, type hints everywhere, `ruff` for lint and format, `bandit` for security lint. Service layer per operation; no business logic in Celery tasks or models.
- **TypeScript strict**; the 3D scene reads only from the store, never from the API.
- **Commits**: [Conventional Commits](https://www.conventionalcommits.org) enforced by commitizen: `feat(workflows): add question gates`. Scopes are app names (`workflows`, `gateway`, `runner`, `frontend`, `docs`). Atomic commits with their tests.
- **No attribution trailers.** Do not add `Co-authored-by:`, `Signed-off-by:` or similar trailers; the commit-msg hook rejects them. Authorship is the commit author; AI assistance needs no trailer.
- **Branches**: `feat/<area>-<short>`, `fix/<short>`, `docs/<short>`; squash-merged into `main` via pull request.
- **Secrets**: `detect-secrets` runs on every commit. Never commit `.env`, keys, or tokens — including in tests (use the fixtures).
- **Language**: code, comments, commit messages, docs and UI strings are in English.

## Pull requests
Use the template. Include: context, what changes, how to test, screenshots for UI, the feature or ADR it relates to. CI must be green (`pre-commit run --all-files`, tests, build). One approval from a maintainer; we may ask for changes or split a large PR.

## Definition of Done
- Tests for new logic (unit; integration if DB/Redis is touched); module coverage ≥ 80 %.
- Events, API or schema changes documented (`docs/`, OpenAPI, event catalog); contract changes noted in the contract's changelog.
- UI changes handle empty, loading and error states and are reachable from the 2D view.
- No new `# noqa` / `# nosec` without a written reason.

## Proposing an ADR
Copy `docs/adr/template.md` to `docs/adr/ADR-XXXX-title.md` with status `proposed`, open a PR with the ADR alone, discuss, then implement in a follow-up PR once it is `accepted`. Superseded decisions are never deleted.

## Reporting bugs and security issues
Bugs: GitHub issues with the template. Security: **do not** open a public issue — see [SECURITY.md](SECURITY.md).
