---
name: jest-patterns
description: "Jest/Vitest patterns for acceptance tests of Node projects: supertest for HTTP, setup files, fake timers. Use when the stack is Node."
dexterhouse:
  schema: 1
  tools_required: []
  cost_hint: low
  rooms: [qa_lab]
---

# Jest / Vitest patterns

- Files `tests/acceptance/*.test.js` (or `.test.ts`); one behaviour per `it`.
- HTTP: `supertest` against the exported app, not a running server.
- Setup and teardown of test data in `beforeEach`/`afterEach`; isolated database per test file when possible.
- Time: `vi.useFakeTimers()` / `jest.useFakeTimers()`.
- Run one file: `npx vitest run tests/acceptance/bookings.test.js` or `npx jest tests/acceptance/bookings.test.js`.
