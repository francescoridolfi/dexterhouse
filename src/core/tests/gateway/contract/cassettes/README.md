# Provider contract cassettes

One folder per provider, one JSON file per scenario. Bodies are in the provider's own wire
format, replayed by an `httpx2.MockTransport` (HTTP providers) or printed by a fake `claude`
executable (`anthropic-cli`). No test ever reaches the network.

```json
{
  "model": "claude-sonnet-5-5",
  "status": 200, "headers": {"content-type": "text/event-stream"},
  "body": ["event: message_start", "data: {...}", ""],
  "expect": {"text": "...", "tool_calls": [{"name": "memory.search", "args": {}}],
             "stop": "tool_use", "usage": {"input": 0, "output": 0, "cached_read": 0, "cached_write": 0},
             "cost_eur": "0.000589", "price_version": "2026-11-01"}
}
```

`anthropic-cli` cassettes carry `stdout` (the stream-json lines) instead of `status`/`body`.
Error scenarios carry `"expect": {"error": {"status", "code", "retryable", "retry_after"}}`.

The cassettes were written by hand from the providers' documented streaming formats
(SSE events, Chat Completions chunks, Ollama NDJSON, Claude Code stream-json 2.1.x); the
`anthropic-cli` authentication cassette reproduces output observed from the real CLI.
To compare with or re-record from real providers, run `test_live.py`:

| Provider | Variables | Rough cost of one run |
|---|---|---|
| `anthropic` | `ANTHROPIC_API_KEY` | < 0.01 USD (Haiku 5.5) |
| `openai` | `OPENAI_API_KEY` | < 0.01 USD (gpt-5-mini) |
| `openai-compatible` | `OPENAI_COMPATIBLE_BASE_URL`, `OPENAI_COMPATIBLE_API_KEY`, `DH_LIVE_COMPATIBLE_MODEL` | endpoint pricing |
| `ollama` | `OLLAMA_BASE_URL`, `DH_LIVE_OLLAMA_MODEL` | free (local) |
| `anthropic-cli` | `DH_LIVE_CLI=1`, an authenticated `claude` on `PATH` | counts against the CLI plan |

```bash
DH_LIVE_TESTS=1 DH_RECORD_CASSETTES=1 uv run pytest src/core/tests/gateway/contract/test_live.py
```

Recorded files land in `cassettes/live/` (git-ignored): remove request ids before copying
them over the hand-written ones.
