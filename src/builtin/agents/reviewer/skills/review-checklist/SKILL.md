---
name: review-checklist
description: "What to check in a task diff: acceptance coverage, correctness, security, tests, readability, scope. Use on every review."
dexterhouse:
  schema: 1
  tools_required: [git.diff]
  cost_hint: low
  rooms: [review_corner]
---

# Review checklist

1. Acceptance: each criterion has a test in the diff (missing = major).
2. Correctness: edge cases, error paths, off-by-one, time zones, concurrency on shared state.
3. Security: secrets, injection, missing authorization, unsafe defaults (blocker).
4. Tests: they assert behaviour, not implementation; they would fail without the change.
5. Layout and naming follow the architecture; no files outside files_hint without a reason in dev_notes.
6. Dependencies: pinned and justified.
7. Readability: small functions, explicit names, errors handled at boundaries.
Out of scope improvements go to out_of_scope_notes, not to findings.
