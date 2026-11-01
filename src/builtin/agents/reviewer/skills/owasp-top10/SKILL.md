---
name: owasp-top10
description: "OWASP Top 10 checks condensed for web application diffs. Use when the task touches authentication, input handling or data access."
dexterhouse:
  schema: 1
  tools_required: [workspace.read]
  cost_hint: medium
  rooms: [review_corner]
---

# OWASP Top 10, condensed

- A01 Broken access control: object-level checks, no IDOR via ids in URLs.
- A02 Cryptographic failures: hashed passwords, TLS assumptions, no home-made crypto.
- A03 Injection: ORM or parameters for SQL, no shell with input, escaped templates.
- A04 Insecure design: rate limits on login, safe defaults.
- A05 Security misconfiguration: DEBUG off, CORS narrow, secure cookies.
- A06 Vulnerable components: pinned, maintained dependencies.
- A07 Identification and authentication failures: session handling, password reset tokens.
- A08 Software and data integrity: no unsigned deserialisation of input.
- A09 Logging failures: security events logged without secrets.
- A10 SSRF: no server-side requests to user-supplied URLs.
Any hit is a blocker unless clearly mitigated.
