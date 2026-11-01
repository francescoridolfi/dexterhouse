---
name: release-notes
description: "How to write release notes only from merged work, test reports and assumptions. Use in the release step."
dexterhouse:
  schema: 1
  tools_required: []
  cost_hint: low
  rooms: [pm_office, release_dock]
---

# Release notes

```
# Release notes — <project> v<version or date>
## Summary            (3 lines: what the client can do now)
## Features           (per requirement id: F-03 Booking with waiting list — T-05)
## Fixes              (fix tasks and the problem they solved)
## Assumptions made   (from the assumptions artifact, with their risk)
## Known issues       (red tests accepted, escalations accepted as-is, open findings)
## How to run         (install, run and test commands from stack.yaml)
## Commits            (hash — message, from the commit log; if missing, say it is not available)
```

Only what is merged and tested. Never invent commit hashes or test numbers: copy them from the inputs.
