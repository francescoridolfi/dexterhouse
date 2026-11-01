---
name: secure-coding-basics
description: "Secure defaults: input validation, authorization on every endpoint, parameterised queries, secrets from the environment. Use on every task that handles input or data."
dexterhouse:
  schema: 1
  tools_required: []
  cost_hint: low
  rooms: [open_space]
---

# Secure coding basics

- Validate input at the boundary (serializers, schemas); reject unknown fields.
- Check authorization on every endpoint and object, not only authentication.
- Use the ORM or parameterised queries; never build SQL or shell commands from input.
- Secrets come from the environment; never commit keys, tokens or passwords (the commit is rejected).
- Escape output in templates; set secure cookie flags; keep DEBUG off outside development.
- Log errors without personal data or secrets.
