# ADR-0014: Skills in the Agent Skills format (SKILL.md)

- Status: accepted · Date: 2026-10-31

## Context
Agents load reusable procedures on demand (progressive disclosure). A widespread convention already exists: a folder with `SKILL.md` (frontmatter `name`, `description`) and supporting files, used by Claude Code and other compatible runtimes.

## Decision
DexterHouse skills adopt that format. Our extensions (e.g. `rooms`, `cost_hint`, `tools_required`) live under the `dexterhouse:` frontmatter key and are ignored by other runtimes. The loader validates with pydantic and shows the agent only `name` + `description` until the skill is requested.

## Alternatives considered
- Our own format: more first-class fields, but zero ecosystem and one more standard to document.

## Consequences
+ Immediate reuse of existing skills; an author of Claude Code skills can publish to the registry without changes.
− Dependency on an external convention: the schema is versioned (`schema: N`) and the loader tolerates unknown fields.
