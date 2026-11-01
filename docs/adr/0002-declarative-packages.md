# ADR-0002: Agents, tools and processes as declarative packages

- Status: accepted · Date: 2026-10-31

## Context
The goal is a community that shares agents through a public marketplace. Installing arbitrary Python code from strangers is an unacceptable risk for an app that has access to LLM keys and git repositories.

## Decision
Installable packages are **data**: YAML + Markdown + assets. Three `kind`s: `agent`, `tool` (descriptor of an MCP server), `process`. The core interprets them; no Python entrypoints in packages in 1.0. See [packages](../packages.md).

## Alternatives considered
- Python plugins with entrypoints (pytest style): maximum power, but sandboxing Python inside the Django process is effectively impossible.
- WASM plugins: excellent isolation, but the ecosystem is immature for this use case.

## Consequences
+ An agent can be written in ten minutes without knowing the core; review in a registry PR is readable.
+ Portable across installations with different LLM providers (model profiles).
− "New" capabilities come only through MCP tools: anyone who needs custom logic writes an MCP server (in any language) and publishes it as a `tool`.
− Requires a versioned schema and strict validation.
