# Licensing FAQ

DexterHouse (core, runner, frontend) is licensed under the **GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later)**. Contributors sign a CLA that lets the maintainer also offer the software under other terms (dual licensing).

## For companies

**Can we use DexterHouse internally without publishing anything?**
Yes. Running AGPL software for your own use — including by your employees and contractors over your internal network — creates no obligation to share anything. Modifying it for internal use does not either.

**We modified DexterHouse and only our employees use it. Do we have to release the changes?**
No. The AGPL's network clause (section 13) applies when you let *users outside your organization* interact with the modified software over a network.

**We want to offer DexterHouse to our customers as a hosted service.**
Then you must offer those users the complete corresponding source of your modified version under the AGPL, including your modifications. If that does not fit your business, a **commercial license** without that obligation is available from the maintainer: licensing@dexterhouse.dev.

**Does the code the agents produce fall under the AGPL?**
No. The output of DexterHouse (the requirements, architecture, code and tests generated for your project) is yours. The AGPL covers DexterHouse itself, not what you make with it, exactly as a compiler's license does not cover your programs. Note that LLM output may be subject to the terms of the model provider you configured.

**Can we connect DexterHouse to our proprietary systems via API, webhooks or MCP tools?**
Yes. Using the documented API, the WebSocket, the CLI, or writing an MCP tool server that DexterHouse talks to does not make your systems derivative works. Linking DexterHouse's Python modules into a proprietary application would.

**Is AGPL allowed in our company?**
Many companies restrict AGPL *redistribution* or *modification for hosted services*, not internal use. Point your legal team to this page and to the exact obligations above.

## For package authors

**What license do my agents, tools and processes have?**
Whatever you choose, declared in `dexterhouse.yaml`. Packages are data (YAML, Markdown, assets) interpreted by DexterHouse; they are not derivative works of it. We recommend MIT or Apache-2.0 so anyone, including companies, can install them.

**An MCP tool server I publish — must it be AGPL?**
No. It is a separate program communicating over a protocol. Use any license; `tool.yaml` just points to it.

**Can I sell packages?**
The public registry lists only openly licensed packages. Private registries (a fork of `dexterhouse-registry` behind your firewall) can hold anything you like.

## For contributors

**Why a CLA?**
So the project can be offered under a commercial license to companies that cannot accept the AGPL, which funds development, while guaranteeing (CLA section 4) that the project always remains available under an OSI-approved license. You keep all rights to your own contribution.

**Which license header goes in new files?**
`SPDX-License-Identifier: AGPL-3.0-or-later` as the first comment line; the pre-commit hook adds it if missing.
