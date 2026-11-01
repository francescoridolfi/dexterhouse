# DexterHouse

**An open-source software house run by AI agents.** Give it a brief; an analyst, an architect, a project manager, developers, a reviewer and a tester take it from requirements to a tested repository, and you watch them do it in a 3D office.

> **Pre-release.** Everything below works from source today; the first tagged release, `v1.0.0`, will publish the Docker images and the `dexterhouse-schema` package. Until then `docker compose up` builds the images locally. See the [roadmap](docs/roadmap.md).

## Why DexterHouse

- **A platform, not a pipeline.** Agents, tools and processes are declarative packages. Install new roles from the public [registry](https://github.com/francescoridolfi/dexterhouse-registry) or publish your own with a pull request.
- **You stay in control.** Per-project `supervised` or `autonomous` mode. Approve requirements, architecture, plan and release, or let it run and get called only when something needs a human.
- **Safe by construction.** Generated code runs only in isolated, network-restricted sandboxes. Agents get exactly the tools their package declares. Pushing to your repo is a system action after your approval, never an agent's decision.
- **Any model.** Anthropic (API or Claude Code CLI), OpenAI, OpenAI-compatible endpoints, Ollama for fully local runs. Agents ask for a *profile* (`strong`, `balanced`, `fast`); you decide what backs it.
- **Costs you can see.** Budget per project, estimate before start, cost per agent, phase and task.

## Quickstart

```bash
git clone https://github.com/francescoridolfi/dexterhouse.git && cd dexterhouse
cp .env.example .env            # add a provider key, or point OLLAMA_BASE_URL to a local Ollama
docker compose up -d --wait
printf 'Owner password: ' && read -rs DH_OWNER_PASSWORD && export DH_OWNER_PASSWORD
docker compose exec -e DH_OWNER_PASSWORD web dexterhouse-manage bootstrap_owner --username admin
```

Secrets are generated on first start. Open http://localhost, sign in as `admin`, paste a brief, pick a mode and a budget, press **Start**. No key at hand? The [demo mode](docs/install.md#connect-a-model) runs a whole project on a fake model. Full guide, TLS and upgrades: [docs/install.md](docs/install.md).

Requirements: Docker Engine 25+ with Compose v2.24+, 4 vCPU / 8 GB RAM recommended, a browser with WebGL 2 for the 3D office (the 2D dashboard works everywhere).

## How it works, in ten lines

1. A **process** (YAML state machine) defines phases, gates and exit criteria; `software-house-default` ships built in.
2. Each phase is run by **agents**: packages made of prompts, skills, allowed tools and an avatar.
3. Agents use **tools** over MCP: workspace files, git, project memory, the marketplace.
4. Every turn is a persisted, idempotent Celery task; nothing lives only in memory.
5. Exit criteria are verified by the core (tests actually run), not claimed by the LLM.
6. Code is written and tested in a per-project **workspace** container managed by a separate **runner** service, the only one with Docker access.
7. Every state change is an **event**; the 3D office and the 2D dashboard are two views of the same stream.
8. Gates pause for you in `supervised` mode; escalations (loops, budget, risky tools) always do.
9. On release, the system opens a pull request (or pushes) to your repository.
10. The retrospective feeds the project memory for the next one.

Architecture decisions are recorded in [docs/adr](docs/adr/README.md); the security model is in [docs/security.md](docs/security.md).

## Documentation

[Install](docs/install.md) · [Use](docs/usage.md) · [API](docs/api.md) · [CLI](docs/cli.md) · [Operate](docs/operations.md) · [Packages](docs/packages.md) · [Write packages](docs/authors.md) · [All docs](docs/README.md)

## Extend it

Write an agent: `dexterhouse pkg init my-reviewer --kind agent`, edit `agent.yaml` and `prompts/system.md`, `dexterhouse-schema validate .`, tag it, then open a pull request to [dexterhouse-registry](https://github.com/francescoridolfi/dexterhouse-registry). Guide: [docs/authors.md](docs/authors.md).

## Repositories

- **dexterhouse** (this repo): everything you install and run. Core (Django, Celery), runner, frontend, built-in agents, processes and tools, package schema, Docker images.
- **dexterhouse-registry**: the public package index, published by pull request.
- The marketplace site and the public documentation site live in a separate project.

## Community

[Contributing](CONTRIBUTING.md) · [Code of Conduct](CODE_OF_CONDUCT.md) · [Security policy](SECURITY.md) · [Roadmap](docs/roadmap.md) · Discussions on GitHub.

## License

DexterHouse (core, runner, frontend) is licensed under the **GNU AGPL-3.0-or-later**. Packages published to the registry keep their own licenses (MIT/Apache recommended). Using DexterHouse internally imposes no obligations; offering it as a network service requires sharing your modifications. Commercial licenses are available from the maintainers. Details: [docs/licensing.md](docs/licensing.md). Contributions require signing the [CLA](CLA.md).
