---
name: conventional-commits
description: "Conventional Commits messages scoped to the task id, as required by git.commit. Use before every commit."
dexterhouse:
  schema: 1
  tools_required: [git.commit]
  cost_hint: low
  rooms: [open_space, qa_lab]
---

# Conventional Commits

`<type>(<scope>): <summary>` in the imperative, at most 72 characters, scope = task id.

| type | when |
|---|---|
| feat | new behaviour (`feat(T-05): book a seat with waiting list`) |
| fix | a bug or a review finding (`fix(T-05): lock course row when booking`) |
| test | tests only (`test(T-05): acceptance tests for bookings`) |
| refactor | no behaviour change |
| docs, chore, build | documentation, tooling, dependencies |

Body (optional): why, not what. No attribution trailers (`Co-authored-by`, `Signed-off-by`).
Small commits: one logical change each. A commit rejected for secrets must be fixed, never forced.
