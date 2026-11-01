# code-review-only

A single phase: the reviewer reads an existing repository in a workspace and produces a
review. The project must provide `stack` (no phase produces it). The `approve_review` gate is
optional: it blocks only when the project marks it `always_required`.
