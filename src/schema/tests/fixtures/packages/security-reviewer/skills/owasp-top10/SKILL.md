---
name: owasp-top10
description: Checklist OWASP Top 10 to apply when reviewing web application code. Use when the task is a security review.
dexterhouse:
  schema: 1
  tools_required: [workspace.read, git.diff]   # la skill è mostrata solo se l'agente li ha
  cost_hint: medium                            # low | medium | high: token aggiunti al contesto
  rooms: [review_corner]                       # opzionale, solo informativo
---

# OWASP Top 10 review
1. Injection: check every query built from user input.
2. Broken access control: check object-level permissions.

The full list is in [the checklist](checklist.md); see also [OWASP](https://owasp.org/Top10/).
