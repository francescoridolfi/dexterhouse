# The `anthropic-cli` provider (Claude Code CLI)

DexterHouse can use the [Claude Code](https://claude.com/claude-code) command line as a
model provider, so a profile runs on the account the CLI is logged into instead of an API key.

> **Your plan's terms are your responsibility.** Using a consumer subscription from an
> automated service may not be covered by the terms of your Anthropic plan. DexterHouse never
> enables this provider by default: you opt in per profile, and the default installation uses
> the `anthropic` provider with an API key.

## Enabling it

1. Install the CLI on the machine that runs the Celery worker (version 2.0 or later) and
   log in once as the worker's user: `claude`, then `/login` (or `claude setup-token`).
   In Docker, mount that user's `~/.claude` read-only and set `CLAUDE_CLI_HOME` to its parent.
2. Create a model profile with provider `anthropic-cli`, a model (`claude-sonnet-5-5`...) and
   the option `{"acknowledge_cli_terms": true}`.

## How it runs

- One `claude -p --max-turns 1 --output-format stream-json` process per model call, in an
  empty temporary directory, with every built-in CLI tool disabled.
- The agent's tools reach the model through `dexterhouse-mcp-bridge`, a local MCP server
  started by the CLI with a 10-minute token. The bridge never runs a tool: DexterHouse does,
  with the same permission checks, logs and events as for every other provider.
- The conversation so far goes in as one user message with one text block per message.
  Earlier blocks never change and nothing follows the last one, so each call reads the
  previous call's prefix from the prompt cache and writes only the new blocks.
- The agent's `limits.max_output_tokens` is passed as `CLAUDE_CODE_MAX_OUTPUT_TOKENS`, and the
  profile option `effort` (`low`...`max`) as `--effort`. The cache TTL is 5 minutes (calls
  of a turn come seconds apart); set the option `cache_ttl: "1h"` to keep the CLI's default.
- At most `CLI_MAX_CONCURRENT` (default 2) processes per worker; `CLI_TIMEOUT_S` (default 600)
  per call. The cost reported by the CLI is recorded with `price_version = "cli"`.

## Errors you may see

| Message | Fix |
|---|---|
| `Claude Code CLI not found` | install it on the worker or set `CLAUDE_CLI_PATH` |
| `Claude Code CLI x.y.z < 2.0.0` | upgrade the CLI |
| `the Claude Code CLI is not authenticated on this worker` | log in again as the worker's user |
| `anthropic-cli is opt-in` | set `acknowledge_cli_terms` on the profile |

Not supported with this provider: images in input, per-call temperature, and
`data_residency: local` (the CLI talks to Anthropic's cloud).
