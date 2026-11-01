---
name: smoke-checklist
description: "How to run the release smoke test: start run_command in background, wait for the port, request the health path, stop. Use in the smoke step."
dexterhouse:
  schema: 1
  tools_required: [workspace.exec]
  cost_hint: low
  rooms: [qa_lab]
---

# Smoke checklist

1. Open the declared port with workspace.open_port.
2. Start `run_command` in background with workspace.exec (`nohup … > /tmp/app.log 2>&1 &`).
3. Poll the port for up to 60 s (`curl -fsS -o /dev/null -w '%{http_code}' http://localhost:<port><healthcheck_path>`).
4. Record status and startup seconds in `smoke`; stop the process.
5. On failure attach the last 50 lines of the log to the failure message.
