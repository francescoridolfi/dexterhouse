# workspace (built-in tool)

Files, shell commands, tests and services inside the project's workspace container. The server
is `dexterhouse-workspace-mcp`, started by the runner in the workspace (uid 1000, no capabilities,
internal network with egress through the proxy allowlist) and reached by the agents through the
tool gateway. Permissions and risks follow the contract in the developer docs
(`contracts/tools/workspace.md`).

`workspace.graph` answers from a deterministic dependency graph of the workspace (Python via
`ast`, JS/TS, Go and Java via import and declaration regexes; no LLM): `summary`, `neighbors`,
`path` and `find`. After each agent commit the core saves the whole graph as the `code_graph`
artifact (`code_graph.json`), and its summary fills the context's workspace tree section.
