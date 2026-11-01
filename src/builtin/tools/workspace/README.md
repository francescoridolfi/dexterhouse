# workspace (built-in tool)

Files, shell commands, tests and services inside the project's workspace container. The server
is `dexterhouse-workspace-mcp`, started by the runner in the workspace (uid 1000, no capabilities,
internal network with egress through the proxy allowlist) and reached by the agents through the
tool gateway. Permissions and risks follow the contract in the developer docs
(`contracts/tools/workspace.md`).
