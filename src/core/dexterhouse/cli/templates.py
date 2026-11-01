# SPDX-License-Identifier: AGPL-3.0-or-later
"""Files written by `dexterhouse pkg init`: the smallest valid package of each kind."""

MANIFEST = """\
schema: 1
kind: {kind}
name: {name}
version: 0.1.0
description: "{title} ({kind} package)"
author: {{ name: "{author}" }}
license: MIT
compat: {{ core: ">=0.1,<2.0" }}
tags: []
"""

README = """\
# {title}

What this {kind} package does, the permissions it needs and why.

Validate it with `dexterhouse pkg validate .`, try it on a development instance with
`dexterhouse pkg install .`, then publish a tag and open a pull request to the registry.
"""

AGENT = """\
schema: 1
role: {ident}
display_name: "{title}"
model_profile: balanced
tools: [memory.search]
skills: []
prompts: {{ system: prompts/system.md }}
output_contract: {{ artifacts: [dev_notes], schema: markdown }}
limits: {{ max_tool_calls: 20, max_output_tokens: 4000, turn_timeout_s: 600 }}
office: {{ room: open_space, color: "#3366cc" }}
"""

SYSTEM_PROMPT = """\
# Role
You are the {title} of a software house run by AI agents.

# Inputs
The task of this turn, the project artifacts and the memory search results.

# Output contract
One Markdown artifact with your result.

# Constraints
Use only the tools you are given.

# Quality bar
Short, specific, verifiable.
"""

TOOL = """\
schema: 1
name: {name}
transport: stdio
runs_in: runner
command: ["uvx", "{name}-mcp@0.1.0"]
permissions:
  - id: {prefix}.read
    mcp_tool: read
    description: "Describe what this permission lets the agent do"
    risk: low
network: none
"""

PROCESS = """\
schema: 1
name: {name}
version: 0.1.0
phases:
  - id: review
    agent: reviewer
    workspace: true
    produces: [review]
    exit: artifacts_present
    gate: {{ id: approve_review, default: optional }}
"""
