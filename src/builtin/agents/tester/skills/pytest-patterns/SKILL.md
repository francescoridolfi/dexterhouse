---
name: pytest-patterns
description: "pytest patterns for acceptance tests: fixtures, parametrize, API client, database isolation, freezing time. Use when the stack is Python."
dexterhouse:
  schema: 1
  tools_required: []
  cost_hint: low
  rooms: [qa_lab]
---

# pytest patterns

- One behaviour per test; arrange-act-assert; explicit minimal data.
- Fixtures in tests/acceptance/conftest.py; prefer factories over shared mutable state.
- `@pytest.mark.parametrize` for input variants instead of loops.
- Django: `pytest-django` with `client` or DRF `APIClient`; `@pytest.mark.django_db`.
- Time: freeze it (`time_machine`/`freezegun`) instead of sleeping.
- Concurrency: threads with a barrier and `transaction=True` databases.
- Run one file: `uv run pytest -q tests/acceptance/test_t05_bookings.py`.
