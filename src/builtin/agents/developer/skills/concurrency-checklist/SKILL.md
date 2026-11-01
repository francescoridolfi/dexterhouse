---
name: concurrency-checklist
description: "Checklist for race conditions on shared resources (capacity, counters, waiting lists, balances). Use when a task changes shared state."
dexterhouse:
  schema: 1
  tools_required: []
  cost_hint: low
  rooms: [open_space]
---

# Concurrency checklist

- Read-check-write on a shared value (seats left, stock, balance) happens in one transaction with a row lock (`SELECT ... FOR UPDATE`, `select_for_update()`), or as a single conditional update.
- Uniqueness is enforced by a database constraint, not only by code.
- Queues and waiting lists have an explicit order (created_at, id) and a promotion step inside the same transaction as the cancellation.
- Side effects (emails) run after commit (`transaction.on_commit`), never inside the locked section.
- Add a test with parallel requests (threads or processes) that would fail without the lock.
