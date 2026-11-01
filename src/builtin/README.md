# Built-in packages

Declarative packages shipped with DexterHouse and seeded at install time:

- `agents/`: analyst, architect, project-manager, recruiter, developer, reviewer, tester
- `skills/`: skills shared by every agent (`markdown-artifacts`, `conventional-commits`,
  `review-format`), listed to an agent when it has the tools they require
- `processes/`: software-house-default, code-review-only
- `tools/`: memory, project, skills (workspace and marketplace arrive with the runner and the
  marketplace)

Each folder is a package (`dexterhouse.yaml` plus its definition) validated by `dexterhouse-schema`,
in the same format as marketplace packages.
