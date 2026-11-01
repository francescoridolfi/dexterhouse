# ADR-0011: Hybrid execution mode per project

- Status: accepted · Date: 2026-10-31

## Context
Human approval at every gate makes the system safe but slow; full autonomy is fast but risky. The project owner chose to leave the choice to the user, per project.

## Decision
`Project.execution_mode ∈ {supervised, autonomous}`. In `supervised`, the process gates with `default: required` wait for the user. In `autonomous`, they are auto-approved and tracked; the user can force individual gates to `always_required`. Escalations (exhausted loops, budget, repeated errors, `risk: high` tools) always open a human gate.

## Alternatives considered
- Supervised only: safe but frustrating for small prototypes.
- Autonomous only: unacceptable for code that ends up in a real repo.
- Numeric autonomy levels (0–5): more flexible but hard to explain.

## Consequences
+ A one-line idea can become a prototype without clicks; a serious project stays under control.
+ The gate data model is identical in both modes: no duplicated logic.
− The UI must make the active mode very visible (a permanent badge in 3D and 2D).
