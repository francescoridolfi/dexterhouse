# git (built-in tool)

The agents' git tools on the workspace repository: status, diff, log, show, add, commit,
checkout of a file, stash. Served by the same `dexterhouse-workspace-mcp` as `workspace`. No
push, merge or branch: the runner does those as system actions after a gate (`git.md` in the
developer docs). `git.commit` runs detect-secrets and refuses `main` and non Conventional
Commit messages.
