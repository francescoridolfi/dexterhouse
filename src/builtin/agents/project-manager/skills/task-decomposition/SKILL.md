---
name: task-decomposition
description: "How to split an architecture into S/M/L vertical-slice tasks with acceptance criteria, dependencies and files_hint. Use when writing or re-planning the task board."
dexterhouse:
  schema: 1
  tools_required: []
  cost_hint: low
  rooms: [pm_office]
---

# Task decomposition

1. T-01 is the scaffold: repository layout from the architecture, dependencies, settings, an empty test suite that runs with `test_command`.
2. One vertical slice per requirement group: model + API/UI + tests. Avoid "all models" or "all endpoints" tasks.
3. Size: S (< 2 h), M (half a day), L (one day). Bigger: split.
4. Acceptance: 2-5 statements a tester can turn into tests ("POST /bookings returns 409 when the course is full").
5. depends_on: only real dependencies (a model the task needs); the graph must be acyclic.
6. files_hint: the files the task creates or changes, following the architecture's layout; tests under tests/.
7. covers: every requirement and story id the task implements. Check that every `must` requirement is covered.
8. assigned_role: only installed roles. In a replan, change only assigned_role (or split a task for the new role), keep ids and approved descriptions.
