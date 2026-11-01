# SPDX-License-Identifier: AGPL-3.0-or-later
"""The demo Recruiter: a real `team_proposal` from the marketplace tools (fake provider).

Rounds, as the prompt's working method asks: (1) the `team-sizing` skill, the board and
`marketplace.search(kind=agent)`; (2) `marketplace.details` of at most two candidates
that are compatible and not high risk; (3) `packages.propose` of the ones whose details
hold up and, in autonomous mode, `packages.install` of the verified low-risk ones; then
the TurnOutput. Each proposed agent takes one task, from the last one backwards. Without
marketplace tools, or with `source: unreachable`, the proposal is empty and says so; the
script key `hire` keeps the older canned proposal of a pre-installed specialist instead.
"""

import json
from typing import Any

from dexterhouse.apps.agents.demo import content
from dexterhouse.apps.gateway.providers.fake import FakeToolCall

QUERY = "frontend developer"
MAX_CANDIDATES = 2
# The tools return null ratings and installs (no marketplace site in 1.0); the team_proposal
# schema requires numbers, so the artifact carries 0 until the site publishes them.
UNKNOWN_METRIC = 0


def _json(text: str | None) -> dict[str, Any]:
    try:
        data = json.loads(text or "")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _candidates(results: dict[str, str]) -> list[dict[str, Any]]:
    found = _json(results.get("search"))
    if found.get("source") in (None, "unreachable"):
        return []
    usable = [
        r
        for r in found.get("results", [])
        if r.get("kind") == "agent" and r.get("compat_ok") and r.get("risk") != "high"
    ]
    return usable[:MAX_CANDIDATES]


def _acceptable(details: dict[str, Any]) -> bool:
    permissions = details.get("permissions") or []
    return (
        bool(details.get("role"))
        and details.get("files") == "ok"
        and not details.get("flags")
        and not details.get("warnings")
        and all(p.get("risk") in ("low", "medium") for p in permissions)
    )


def _proposals(turn: Any, results: dict[str, str]) -> list[dict[str, Any]]:
    task_ids = list(reversed(turn.inputs.task_ids or []))
    chosen = []
    for candidate in _candidates(results):
        details = _json(results.get(f"details:{candidate['name']}"))
        if not _acceptable(details) or len(chosen) >= len(task_ids):
            continue
        chosen.append(
            {
                "name": details["name"],
                "version": details["version"],
                "role": details["role"],
                "reason": f"A {details['role'].replace('_', ' ')} does this task better "
                "than the generic developer.",
                "for_tasks": [task_ids[len(chosen)]],
                "permissions": [
                    {"id": p["id"], "risk": p["risk"]} for p in details.get("permissions", [])
                ],
                "risk": details["risk"],
                "verified": bool(details["verified"]),
                "rating": UNKNOWN_METRIC,
                "installs": UNKNOWN_METRIC,
                "author_github": details["author"],
            }
        )
    return chosen


def next_calls(turn: Any, results: dict[str, str], rounds: int) -> list[FakeToolCall]:
    """The tool calls of round `rounds` (0-based), or [] when it is time to answer."""
    if rounds == 0:
        calls = []
        if "skills.read" in turn.tools:
            calls.append(FakeToolCall(id="skill", name="skills.read", args={"name": "team-sizing"}))
        if "project.tasks" in turn.tools:
            calls.append(FakeToolCall(id="tasks", name="project.tasks", args={}))
        if "marketplace.search" in turn.tools:
            args = {"query": QUERY, "kind": "agent", "limit": 5}
            calls.append(FakeToolCall(id="search", name="marketplace.search", args=args))
        return calls
    if rounds == 1 and "marketplace.details" in turn.tools:
        return [
            FakeToolCall(
                id=f"details:{c['name']}", name="marketplace.details", args={"name": c["name"]}
            )
            for c in _candidates(results)
        ]
    if rounds == 2:
        chosen = _proposals(turn, results)
        calls = []
        if chosen and "packages.propose" in turn.tools:
            entries = [
                {k: p[k] for k in ("name", "version", "reason", "for_tasks")} for p in chosen
            ]
            calls.append(
                FakeToolCall(id="propose", name="packages.propose", args={"proposals": entries})
            )
        if "packages.install" in turn.tools:
            calls += [
                FakeToolCall(
                    id=f"install:{p['name']}",
                    name="packages.install",
                    args={"name": p["name"], "version": p["version"]},
                )
                for p in chosen
                if p["verified"] and p["risk"] == "low"
            ]
        return calls
    return []


def output(turn: Any, results: dict[str, str]) -> dict[str, Any]:
    """The TurnOutput with `team_proposal.json`."""
    found = _json(results.get("search"))
    if turn.script.get("hire") and not _candidates(results):
        data = content.team_proposal(True, turn.inputs.task_ids or [], reachable=True)
    else:
        data = _from_marketplace(turn, results, found)
    artifact = {"kind": "team_proposal", "name": "team_proposal.json", "data": data}
    return {"status": "done", "summary": data["summary"][:400], "artifacts": [artifact]}


def _from_marketplace(turn: Any, results: dict[str, str], found: dict[str, Any]) -> dict:
    source = found.get("source")
    if source in (None, "unreachable"):
        return {
            "marketplace_status": "unreachable",
            "proposals": [],
            "summary": "Marketplace unreachable or its tools unavailable: built-in team only.",
        }
    proposals = _proposals(turn, results)
    installed = [
        f"{p['name']}@{p['version']}"
        for p in proposals
        if _json(results.get(f"install:{p['name']}")).get("status") == "installed"
    ]
    flagged = [
        name.removeprefix("details:")
        for name, text in results.items()
        if name.startswith("details:") and _json(text).get("flags")
    ]
    summary = f"{len(proposals)} specialist(s) proposed from {found.get('total', 0)} matches."
    if installed:
        summary += f" Installed: {', '.join(installed)}."
    if flagged:
        summary += f" Ignored instructions found in the README of {', '.join(flagged)}."
    data: dict[str, Any] = {
        "marketplace_status": "reachable" if source == "index" else "degraded",
        "proposals": proposals,
        "summary": summary,
    }
    if installed:
        data["installed"] = installed
    return data
