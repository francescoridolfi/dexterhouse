# ADR-0003: MCP as the only protocol for tools

- Status: accepted · Date: 2026-10-31

## Context
Agents need concrete capabilities (filesystem, git, shell, browser, marketplace). Inventing our own format means zero ecosystem on day one.

## Decision
Every tool is an **MCP server** (Model Context Protocol). The core is an MCP client; `tool` packages describe how to start or reach the server and which permissions it exposes. The built-in tools (`workspace`, `marketplace`) are MCP servers too.

## Alternatives considered
- Provider-native function calling with an internal registry: simpler, but tied to the provider and not extensible by third parties.
- Proprietary HTTP plugins: they reinvent MCP.

## Consequences
+ Immediate reuse of existing MCP servers (git, filesystem, browser, Jira, Slack...).
+ The same tool works with the `anthropic-cli` provider (which speaks MCP natively).
− Process overhead for stdio servers: handled with per-workspace pools and lifecycle management in the runner.
− MCP permissions are coarse: we refine them with our own `permissions` map in the manifest.
