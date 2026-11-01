---
name: requirements-elicitation
description: "Which questions to ask about a brief, by domain, and when an assumption is enough. Use before deciding between questions and assumptions."
dexterhouse:
  schema: 1
  tools_required: [project.ask]
  cost_hint: low
  rooms: [meeting_room]
---

# Requirements elicitation

Ask only when the answer changes the requirements (scope, data, roles, compliance). Otherwise assume and write it down.

## Checklist per brief
1. Actors: who uses the system, with which roles and permissions? Is there an administrator?
2. Core entities and their lifecycle: what is created, changed, deleted, archived?
3. Money: payments, invoices, refunds? (changes compliance and data model)
4. Identity: sign-up, login, password reset, single sign-on?
5. Notifications: email, SMS, push? Which events trigger them?
6. Language and locale of the UI, time zones, currencies.
7. Volumes: users, records, peak requests; expected response times.
8. Data protection: personal data, retention, export and deletion requests.
9. Integrations: external systems, imports, exports.
10. Delivery constraints declared by the client (hosting, Docker, stack): record, do not decide.

## Writing a question
- `kind: choice` with 2-4 options whenever possible; `boolean` for yes/no; `text` only if open.
- `why`: one line on what changes depending on the answer.
- `default_assumption`: what you will write if nobody answers. It must be safe and small.

## Writing an assumption
`assumed` is a decision, not a question; `risk` is high when a wrong guess changes the data model or the cost.
