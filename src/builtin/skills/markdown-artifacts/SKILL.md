---
name: markdown-artifacts
description: "Common rules for every artifact: names, stable ids (F-xx, US-xx, T-xx, R-n), templates, and the TurnOutput that ends a turn. Use when unsure how to shape an artifact."
dexterhouse:
  schema: 1
  tools_required: []
  cost_hint: low
---

# Markdown artifacts and the TurnOutput

- One artifact per (kind, name); the platform versions it. Keep the same name to publish a new version.
- Names: requirements.md, user_stories.md, architecture.md, adr/000N-slug.md, stack.yaml, task_board.json, team_proposal.json, questions.json, assumptions.json, dev_notes/T-xx-iterN.md, reviews/T-xx-iterN.md, test_reports/T-xx-iterN.json, release_notes.md, retrospective.md.
- Ids are the thread across phases: cite F-xx, US-xx, T-xx and R-n of the previous phases; never renumber.
- Structured kinds carry `data` (JSON matching the schema); the others carry Markdown `content` with the template's `##` sections in order.
- The turn ends with one JSON object: status, summary (<= 400 characters), artifacts, verdict (reviewer and tester only), handoff, blocked_reason (only when blocked), assumptions_made.
