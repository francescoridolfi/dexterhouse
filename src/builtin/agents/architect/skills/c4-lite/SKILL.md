---
name: c4-lite
description: "A light C4 (context and containers) description in Markdown and Mermaid for the Overview section. Use when drawing the architecture overview."
dexterhouse:
  schema: 1
  tools_required: []
  cost_hint: low
  rooms: [design_studio]
---

# C4 lite

Overview = level 2 (containers) only; level 1 in one sentence.

```mermaid
flowchart LR
  user([Member]) --> web[Web app<br/>Django templates]
  web --> api[REST API<br/>Django REST framework]
  api --> db[(PostgreSQL)]
  api --> mail[[SMTP / mailpit]]
```

Then a table: container | technology | responsibility | requirements.
Name containers after what they do, not after the technology. Show external systems at the edge. Do not draw classes or deployment details here.
