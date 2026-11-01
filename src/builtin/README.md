# Built-in packages

Declarative packages shipped with DexterHouse and seeded at install time:

- `agents/`: analyst, architect, project_manager, recruiter, developer, reviewer, tester
- `processes/`: software-house-default, code-review-only
- `tools/`: workspace, marketplace, memory

Each folder is a package (`dexterhouse.yaml` plus its definition) validated by `dexterhouse-schema`.
They are added epic by epic; this folder is intentionally empty in Sprint 0.
