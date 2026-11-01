# ADR-0010: Registry on GitHub + separate marketplace site

- Status: accepted · Date: 2026-10-31

## Context
The marketplace must exist from 1.0, be public, free to operate, and support private company registries. The project owner wants a separate site and an agent that searches and recommends packages during planning.

## Decision
- Source of truth: the `dexterhouse-registry` repo (JSON index, publishing via PR, validation CI), following the Obsidian/Homebrew model.
- `dexterhouse-marketplace` site: a separate Django project with search, ratings, statistics, badges and a public API; it syncs from the registry.
- The core talks to the site's API and, as a fallback, to the raw index on GitHub. The URL is configurable (private registries).
- The Recruiter agent uses the `marketplace.search` MCP tool. See [recruiter](../recruiter.md) and [authors](../authors.md).

## Alternatives considered
- Site with uploads only: depends on a central server, not forkable, hosting costs for files.
- GitHub only, no site: no decent search, ratings or telemetry.
- Hugging Face Hub as storage: interesting, but ties us to a third-party vendor.

## Consequences
+ Zero cost for package storage; public audit of every publication.
+ Companies can point the core at a private fork of the registry.
− Two more repos to maintain; site hosting must be funded (decision CD-040).
− Moderation is needed: registry policy and maintainers from the start.
