# Security Policy

## Supported versions
| Version | Supported |
|---|---|
| 1.x (latest minor) | yes |
| older minors | critical fixes only for 90 days after the next minor |
| pre-1.0 | no |

## Reporting a vulnerability
Please **do not** open a public issue. Report privately through GitHub's *Report a vulnerability* (Security Advisories) on this repository, or email **security@dexterhouse.dev** (PGP key in `docs/security/pgp.asc`). Include: affected component (core, runner, workspace images, frontend, marketplace, registry CI, a specific package), version, reproduction steps, impact, and any proof of concept. We welcome reports in English or Italian.

## What to expect
| Step | Target |
|---|---|
| Acknowledgement | within 3 business days |
| Triage and severity (CVSS 3.1) | within 7 days |
| Fix for Critical/High | within 30 days, with a coordinated release and advisory |
| Fix for Medium/Low | next minor release |
| Public disclosure | after the fix is released, or 90 days after the report, whichever comes first (negotiable for complex cases) |

We credit reporters in the advisory unless they prefer otherwise. There is no bug bounty program at this time.

## Scope
In scope: everything in this repository, the published Docker images, the runner protocol, the workspace sandbox (escape, network egress, privilege escalation), the frontend, the marketplace site and API, the registry CI, and the package validation pipeline.
Out of scope: vulnerabilities in third-party LLM providers, in packages published by third parties to the registry (report those via the marketplace *Flag* button — see `POLICY.md`), social engineering, denial of service against the public marketplace, and findings that require a compromised host or Docker daemon.

## Safe harbor
Research conducted in good faith, within scope, without exfiltrating data, disrupting the public marketplace or targeting other users' installations, will not lead to legal action from the maintainers. Test against your own installation.

## Security design
Threat model, controls and the automated security test suite are documented in `docs/security/`. Known accepted risks are listed there and reviewed at every release.
