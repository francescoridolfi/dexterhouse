# LLM providers

Agents ask for a **profile** (`strong`, `balanced`, `fast`, plus `embed` for the project
memory), never for a model. Each organization maps profiles to a provider and a model in
`ModelProfile` (admin: *LLM gateway → Model profiles*), and a project can override a profile.
Without any row the installation defaults to Anthropic through its API:

| Profile | Default |
|---|---|
| `strong` | `anthropic` / `claude-opus-5-5` |
| `balanced` | `anthropic` / `claude-sonnet-5-5` |
| `fast` | `anthropic` / `claude-haiku-5-5` |
| `embed` | Ollama `mxbai-embed-large` if reachable, else OpenAI `text-embedding-3-small` (1024 dimensions) |

| Provider | Configuration | Notes |
|---|---|---|
| `anthropic` | `ANTHROPIC_API_KEY` | prompt caching on the stable part of the prompt; no embeddings |
| `anthropic-cli` | an authenticated `claude` CLI on the worker, explicit opt-in | see [anthropic-cli.md](anthropic-cli.md) |
| `openai` | `OPENAI_API_KEY` | also the embedding fallback |
| `openai-compatible` | `base_url` in the profile or `OPENAI_COMPATIBLE_BASE_URL`, key in `OPENAI_COMPATIBLE_API_KEY` | vLLM, LM Studio, Groq, OpenRouter...; mark it *local* for `data_residency: local` |
| `ollama` | `OLLAMA_BASE_URL` | local; the only cloud-free option with `data_residency: local` |

API keys are read from the environment only: a profile may name another variable in
*API key env* (for example `OPENAI_KEY_TEAM_B`), never the key itself.

Profile options: `temperature`, `max_tokens`, `allow_downgrade` (when the provider is down,
`strong` falls back to `balanced`, then `fast`), `effort` (`anthropic` and `anthropic-cli`), `tools: false` for
models without tool use, `refusal_fallback: false` to disable Anthropic's server-side
fallback on refusals.

Every call is recorded as an `LLMCall` with tokens, cost in EUR (prices in
`prices.yaml`, USD converted with `FX_EUR_PER_USD`) and latency. Failing providers are
retried (2, 4, 8 s; `retry-after` on 429) and a circuit breaker stops calling a provider for
two minutes after five failures in a minute.

## Demo without an LLM

The `fake` provider never calls the network. With
`GATEWAY_FAKE_RESPONDER=dexterhouse.apps.agents.demo.respond` in `.env` and every profile of
the organization mapped to provider `fake` (model `fake-model`, `embed` model `hash-1024`),
the built-in agents answer deterministically: a whole project runs through every phase and
gate, with artifacts that follow the real templates and say they come from the demo.
