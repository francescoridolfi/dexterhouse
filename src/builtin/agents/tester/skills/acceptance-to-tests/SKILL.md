---
name: acceptance-to-tests
description: "How to map each acceptance criterion to an automated test in tests/acceptance/ and report coverage. Use at the start of each tester turn."
dexterhouse:
  schema: 1
  tools_required: [workspace.write]
  cost_hint: low
  rooms: [qa_lab]
---

# From acceptance criteria to tests

1. List the criteria of the task; give each a test name after the behaviour.
2. Check the tree: reuse fixtures, do not duplicate the developer's tests.
3. Write the tests under tests/acceptance/ (file per task: tests/acceptance/test_t05_bookings.py), only test files and fixtures.
4. Run them alone, then the full suite with workspace.run_tests.
5. coverage_notes: "criteria 1-3 proven by …; criterion 4 not testable because …".
6. Commit with `test(T-05): acceptance tests for …`.
