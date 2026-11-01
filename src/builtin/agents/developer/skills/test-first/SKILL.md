---
name: test-first
description: "Write the tests for the acceptance criteria before the code, then make them pass in small steps. Use at the start of each task."
dexterhouse:
  schema: 1
  tools_required: [workspace.exec]
  cost_hint: low
  rooms: [open_space]
---

# Test first

1. Turn each acceptance criterion into one test named after the behaviour (`test_full_course_returns_409`).
2. Run it and see it fail for the right reason (`workspace.exec` with the single test).
3. Write the smallest code that makes it pass; run again.
4. Refactor with the tests green; commit.
5. At the end run the full suite with `workspace.run_tests` and copy the summary into dev_notes "How verified".

Your tests live next to the code or in tests/, never in tests/acceptance/ (the tester's).
