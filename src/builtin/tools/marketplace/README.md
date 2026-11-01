# marketplace

Built-in tools `marketplace.search` and `marketplace.details`, used by the Recruiter during
planning. In 1.0 they read the registry index (`REGISTRY_INDEX_URL`) and the package files at
their tag; ratings and installs are `null` until the marketplace site exists. Every text that
comes from a package is wrapped in `<<untrusted source="marketplace">>` blocks.
Server: `dexterhouse.apps.agents.builtin_mcp` (group `marketplace`).
