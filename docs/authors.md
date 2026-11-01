# Publishing packages

Anyone can publish an agent, a tool (an MCP server descriptor) or a process for
DexterHouse. A package lives in your own public git repository; the
[registry](https://github.com/francescoridolfi/dexterhouse-registry) only lists it, and
publishing is a pull request there. See [packages.md](packages.md) for how packages are
installed and checked.

## 1. Create the package

```bash
dexterhouse pkg init my-agent --kind agent   # or copy templates/agent-starter from the registry
```

The manifest `dexterhouse.yaml` sits at the root:

| Field | Rule |
|---|---|
| `name` | `^[a-z][a-z0-9-]{2,63}$`, unique in the registry, never changes |
| `kind` | `agent`, `tool` or `process` (with `agent.yaml`, `tool.yaml` or `process.yaml`) |
| `version` | semver `X.Y.Z`; every release is a new version |
| `description`, `tags` | at most 200 characters, at most 10 tags; copied into the index |
| `author.github` | your GitHub login: the registry pull request must come from it |
| `license` | an OSI-approved SPDX id (MIT or Apache-2.0 recommended), plus a `LICENSE` file |
| `compat.core` | PEP 440 range of supported cores, e.g. `">=1.0,<2.0"` |

Packages are declarative: YAML, Markdown and images or glTF only, at most 20 MB, no
executables or symlinks. Prompts and skills must not tell agents to ignore permissions,
gates or the system prompt. A **tool** starts its MCP server with `uvx`, `npx`, `python`
or `node` and a pinned package (`mcp-server-git@0.6.2`); its permissions declare a risk
(`low`, `medium`, `high`).

## 2. Check it locally

`dexterhouse-schema` runs the same checks as the core installer and the registry CI.
Until it is on PyPI, run it from this repository:

```bash
alias dexterhouse-schema='uvx --from "git+https://github.com/francescoridolfi/dexterhouse#subdirectory=src/schema" dexterhouse-schema'
dexterhouse-schema validate .
dexterhouse-schema scan-prompts .
```

To try it in a running core: `dexterhouse pkg install ./my-agent --org <slug>` (development,
`PACKAGES_ALLOW_LOCAL=true`) or, once tagged, `dexterhouse pkg install git+https://github.com/<you>/my-agent@v0.1.0`.

## 3. Tag and hash

```bash
git tag v0.1.0 && git push origin v0.1.0
dexterhouse-schema hash . --ref v0.1.0
```

`hash` prints the sha256 of `git archive --format=tar v0.1.0`, which is exactly what the
installer downloads and verifies. Never move or rewrite a published tag: the daily registry
recheck would flag the version and it would be yanked.

## 4. Open the registry pull request

Fork the registry and add `packages/my-agent.json`:

```json
{
  "schema": 1,
  "name": "my-agent",
  "kind": "agent",
  "repo": "https://github.com/<you>/my-agent",
  "author_github": "<you>",
  "description": "Same text as in dexterhouse.yaml",
  "tags": ["example"],
  "risk": "low",
  "versions": [
    { "version": "0.1.0", "ref": "v0.1.0", "sha256": "<output of hash>",
      "compat_core": ">=0.1,<2.0", "published_at": "2026-11-01T10:00:00Z", "signature": null }
  ],
  "verified": false,
  "deprecated": false,
  "replaced_by": null
}
```

`risk` is the risk shown in search results: for a tool, at least its highest permission
risk. Check the entry with `dexterhouse-schema check-entry packages/my-agent.json <checkout>`,
then open the pull request from the `author_github` account. CI clones the tag, compares
the hash, validates the package, scans it for secrets and forbidden prompt patterns and
posts a summary; a maintainer reviews and merges, and `index.json` is regenerated within
minutes.

**New version:** tag it, append it to `versions` (ascending, greater than the last one) and
open a new pull request. Published versions are never edited or removed.
**Deprecation:** set `deprecated: true` and optionally `replaced_by`; a maintainer applies it.

## 5. The verified badge

`verified` means a maintainer reviewed the prompts, skills and permissions and your GitHub
account has two-factor authentication. Ask for it on the marketplace once it is online,
until then with an issue titled `verified: <name>` in the registry. In `autonomous` mode
DexterHouse only auto-installs verified, low-risk packages. A new version that changes
permissions is re-reviewed.

## Private registries

A company can fork the registry (privately if needed), publish internal packages through
pull requests with the same CI, and point its cores at the fork:

```bash
# .env of the core
REGISTRY_INDEX_URL=https://registry.internal.example/index.json
# or a file mounted into the core containers
REGISTRY_INDEX_URL=file:///srv/registry/index.json
```

The core verifies every git install against that index (same repository, tag and sha256)
and refuses git installs when the index cannot be read and no saved copy exists. An empty
`REGISTRY_INDEX_URL` disables the verification, for offline installs only.
