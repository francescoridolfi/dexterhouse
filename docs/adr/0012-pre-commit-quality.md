# ADR-0012: Code quality and security via pre-commit

- Status: accepted · Date: 2026-10-31

## Context
The project owner requires senior-engineer standards; the project handles secrets and produces code, so every commit must pass automated local checks, not only in CI.

## Decision
`pre-commit` is mandatory, with: **commitizen** (Conventional Commits, `cz check` on `commit-msg`, automatic versioning), **detect-secrets** (with a baseline), **ruff** (lint + format, replacing black/isort/flake8), **bandit** (Python SAST), plus standard hooks (yaml, EOF, whitespace, large files, merge conflicts). Frontend: eslint + prettier + tsc. **No `Co-authored-by` trailer** in commits. CI runs the same hooks (`pre-commit run --all-files`).

## Alternatives considered
- CI only: late feedback, dirty commits in history.
- black + isort + flake8 + pylint: ruff replicates all of them in a tenth of the time.
- semantic-release instead of commitizen: great for Node; commitizen is Python-native.

## Consequences
+ Readable git history, automatic changelog, semver releases from `cz bump`.
+ Secrets blocked before they leave the machine.
− Onboarding: `pre-commit install` documented in the contributing guide.
− Bandit produces false positives: justified `# nosec` comments and explicit exclusions in `pyproject`.
