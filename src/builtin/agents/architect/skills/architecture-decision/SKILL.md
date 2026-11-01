---
name: architecture-decision
description: "How to write an ADR in MADR style (context, decision, alternatives, consequences) that cites requirement ids. Use for the stack ADR and the riskiest domain decision."
dexterhouse:
  schema: 1
  tools_required: []
  cost_hint: low
  rooms: [design_studio]
---

# Architecture decision records

Name: `adr/000N-slug.md`, numbered from 0001 in the order you write them; never renumber.

```
# ADR-0002 — Waiting list promotion in the booking transaction
- Status: accepted · Date: <today> · Requirements: F-04, N-01
## Context
What forces the decision: requirements, constraints, risks.
## Decision
One paragraph, in the present tense.
## Alternatives considered
- Option and why it lost (cost, complexity, a requirement it fails).
## Consequences
+ What gets easier. − What gets harder, and how it is mitigated.
```

Write at least two: the stack choice and the riskiest domain decision (concurrency, money, security, data loss). An ADR that cites no requirement id is not justified.
A "no" is also a decision: no cache, no queue, no microservices, with the reason.
