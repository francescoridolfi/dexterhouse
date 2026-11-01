---
name: review-format
description: "The review protocol shared by developer, reviewer and tester: finding ids R-n numbered across iterations, severities, resolution and responses. Use when writing or answering a review."
dexterhouse:
  schema: 1
  tools_required: [git.diff]
  cost_hint: low
  rooms: [open_space, review_corner, qa_lab]
---

# Review format

- Findings `R-n`, numbered across iterations of the same task: the next new finding follows the last id used.
- Severity: blocker (security, data loss, broken acceptance), major (missing test for a criterion, wrong behaviour), minor, nit. Only blocker and major block.
- Iteration 2: no new minor or nit. Iteration 3 and later: only new blockers.
- A finding names file and line or symbol, the change (`request`) and how to verify it (`how_to_verify`).
- Carried findings keep id and first_seen_iteration; `resolved: true` when the diff shows the fix.
- `blocking_count` = open blocker + major; verdict request_changes iff blocking_count >= 1.
- Developer responses in dev_notes, one line per open finding or failing test: `R-3: done — …`, `R-4: done differently: …`, `R-5: disputed: …`.
- Tester failures may cite `related_finding: R-3`.
