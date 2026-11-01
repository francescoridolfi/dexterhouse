---
name: nfr-checklist
description: "Non-functional requirements to consider (performance, security, accessibility, language, data protection) with measurable phrasing. Use before closing requirements.md."
dexterhouse:
  schema: 1
  tools_required: []
  cost_hint: low
  rooms: [meeting_room]
---

# Non-functional requirements checklist

Write each one with a number or a verifiable condition.

| Area | Example phrasing |
|---|---|
| Performance | N-01 95% of API requests answer in under 300 ms with 50 concurrent users. |
| Availability | N-02 The app restarts automatically after a crash (container restart policy). |
| Security | N-03 Passwords are stored hashed with a slow algorithm; no secret is committed. |
| Authorization | N-04 Every endpoint checks the caller's role; members cannot see other members' data. |
| Accessibility | N-05 Pages meet WCAG 2.1 AA for contrast and keyboard navigation. |
| Language | N-06 The UI is in Italian; dates use the Europe/Rome time zone. |
| Data protection | N-07 A member can export and delete personal data on request. |
| Operability | N-08 The project starts with one documented command (Docker Compose). |
| Observability | N-09 Errors are logged with a request id. |

Unknown numbers go to Open points with the value you assumed.
