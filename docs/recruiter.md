# The Recruiter

During planning the Recruiter reads the task board and looks in the marketplace for
specialist agents that would do some tasks markedly better than the built-in team. It only
proposes: people (or, in autonomous mode, a strict policy) decide what gets installed.
Zero proposals is a normal outcome.

## When it runs

Planning has three steps: the project manager writes the task board, the Recruiter writes
`team_proposal.json`, and the gate `approve_plan` shows both. If the gate hires someone, the
project manager re-plans (`replan`) and assigns the tasks the new agents were proposed for.

## Where it looks

In 1.0 the marketplace is the registry index (`REGISTRY_INDEX_URL`, see
[packages](packages.md)). For each candidate the Recruiter reads the package files at their
tag: the README, the manifest and `agent.yaml` (role, room, required tools). Files come from
`raw.githubusercontent.com` for GitHub repositories; set `MARKETPLACE_RAW_URL` for another
host, for example `https://git.example.com/{path}/-/raw/{ref}/{file}`. The core talks to no
other host. Ratings and installs are not published yet, so proposals leave them empty.

| Setting | Default | Meaning |
|---|---|---|
| `REGISTRY_INDEX_URL` | empty | registry index; empty means no marketplace |
| `MARKETPLACE_RAW_URL` | empty | package file URL template (`{host}`, `{path}`, `{ref}`, `{file}`) |
| `PACKAGES_GIT_MIRRORS` | `{}` | JSON `{"https://github.com/": "https://mirror.example.com/"}`: clone from a mirror; hashes are still checked against the index |
| `MARKETPLACE_URL` | empty | reserved for the marketplace site API (not used in 1.0) |

Searches are cached for 5 minutes and package files for 1 hour. If the registry cannot be
reached the last saved copy of the index is used (`degraded`); with no copy the Recruiter
reports the marketplace as unreachable, proposes nothing and the project continues with the
built-in team.

Texts from packages are untrusted. They reach the Recruiter wrapped as
`<<untrusted source="marketplace">>` blocks, and a README that addresses agents ("ignore your
instructions", "call packages.install") is flagged, logged and not proposed.

## What a proposal contains

At most three proposals. Each names the package and version, the role it adds, the tasks
it is for and why the built-in developer or tester is not enough, the permissions it
requires with their risk, whether it is verified, and the author. Packages that need a
`risk: high` permission, are incompatible with this core, or are processes are never
proposed.

## What the gate shows and does

The `approve_plan` gate lists the proposed specialists above the artifacts: package,
tasks, permissions, trust (verified, risk, author) and the reason. Then:

- **Supervised**: approving the plan installs every proposed package (your approval is the
  consent to the listed permissions) and hires one agent per package. Rejecting or approving
  with comments sends planning back to the team.
- **Autonomous**: the Recruiter itself installs the proposals that are verified with risk low
  (`packages.install`); the gate approves automatically and installs nothing else, so
  unverified or medium-risk proposals stay proposals. An admin can install them later.

A hired agent enters the office from the HR room (`agent.hired`, `source: marketplace`) with
the tools listed in the proposal, and stays on the version it was hired with until the
project ends.

## API

`GET /api/v1/marketplace/search?q=&kind=&tags=a,b&verified=true&limit=`,
`GET /api/v1/marketplace/packages/{name}` and `GET /api/v1/marketplace/status` use the same
client as the Recruiter; the header `X-Marketplace-Source` says where the answer came from
(`index`, `cache` or `unreachable`).
