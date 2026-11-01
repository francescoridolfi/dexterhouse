# ADR-0008: Multi-provider LLM gateway with model profiles

- Status: accepted · Date: 2026-10-31

## Context
The project owner wants multiple providers from day zero, with Anthropic reachable both through the API and through the Claude Code CLI. Shared agents must work on installations with different providers.

## Decision
A `gateway` module with a uniform `Provider` interface and the providers `anthropic`, `anthropic-cli`, `openai`, `openai-compatible`, `ollama`. Agents declare a **profile** (`strong|balanced|fast`); the installation maps profiles to provider + model. Every call is tracked in `LLMCall` with its cost. See [providers](../providers/README.md).

## Alternatives considered
- LiteLLM as a dependency: covers many providers but not the CLI case, adds a large dependency and hides tool-use details we need.
- A single provider in 1.0: rejected by the project owner.

## Consequences
+ No lock-in; offline installations with Ollama; costs comparable across providers.
+ The CLI provider lets users use their Claude Code subscription and its MCP ecosystem.
− Each provider has different tool-use semantics: a normalization layer that needs thorough testing.
− The CLI provider depends on an external binary and its terms of use (decision CD-012).
