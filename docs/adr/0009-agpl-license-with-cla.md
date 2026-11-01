# ADR-0009: AGPL-3.0 license with CLA

- Status: accepted · Date: 2026-10-31

## Context
The project is open source, but the project owner wants to keep the exclusive option of offering it as SaaS and to prevent third parties from reselling it as closed software. The repo started with Apache 2.0 (from a template), which would allow exactly that.

## Decision
**AGPL-3.0-or-later** for the core, the runner and the frontend. A **Contributor License Agreement** (CLA) is mandatory for external contributors, granting enough rights to let the copyright holder dual-license. The marketplace site follows the same license. **Packages** (agents, processes, tools) are not derivative works: the registry recommends MIT/Apache for packages and states this in its terms. See [licensing](../licensing.md).

## Alternatives considered
- Apache 2.0 / MIT: maximum adoption, zero protection from a "SaaS reseller".
- BSL / SSPL: more protective but not open source by OSI standards; they would hurt the marketplace community.
- AGPL without CLA: protects from resellers but also prevents the holder from relicensing.

## Consequences
+ Anyone offering DexterHouse as a service must release their changes; the holder can offer a commercial license.
+ Compatible with Django (BSD), Celery (BSD), React (MIT).
− Some companies avoid AGPL even for internal use: the docs must explain that internal use imposes no obligations.
− The CLA adds friction for contributors (CLA-assistant bot on GitHub).
− Action: replace `LICENSE`, add SPDX headers and `CLA.md`.
