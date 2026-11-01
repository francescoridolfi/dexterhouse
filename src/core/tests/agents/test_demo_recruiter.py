# SPDX-License-Identifier: AGPL-3.0-or-later
"""The demo Recruiter's rounds and output, without processes (the slow e2e runs them)."""

import json
from types import SimpleNamespace

from dexterhouse.apps.agents.demo import recruiter

ALL_TOOLS = {
    "skills.read",
    "project.tasks",
    "marketplace.search",
    "marketplace.details",
    "packages.propose",
    "packages.install",
}


def turn(tools=ALL_TOOLS, script=None, task_ids=("T-01", "T-02")):
    inputs = SimpleNamespace(task_ids=list(task_ids))
    return SimpleNamespace(tools=set(tools), script=script or {}, inputs=inputs)


def hit(name, **extra):
    return {"name": name, "kind": "agent", "compat_ok": True, "risk": "low", **extra}


def details(name, verified=True, **extra):
    return {
        "name": name,
        "version": "1.0.0",
        "role": name.replace("-", "_"),
        "files": "ok",
        "flags": [],
        "warnings": [],
        "permissions": [{"id": "project.tasks", "risk": "low", "available": True}],
        "risk": "low",
        "verified": verified,
        "author": "janedoe",
        **extra,
    }


SEARCH = {
    "source": "index",
    "total": 4,
    "results": [
        hit("vue-dev"),
        hit("react-dev"),
        hit("risky-dev", risk="high"),
        {**hit("old-dev"), "compat_ok": False},
    ],
}


def results(**extra):
    base = {
        "search": json.dumps(SEARCH),
        "details:vue-dev": json.dumps(details("vue-dev")),
        "details:react-dev": json.dumps(details("react-dev", verified=False)),
    }
    return {**base, **extra}


def test_rounds_search_then_details_then_propose_and_install():
    first = recruiter.next_calls(turn(), {}, 0)
    assert [c.name for c in first] == ["skills.read", "project.tasks", "marketplace.search"]
    second = recruiter.next_calls(turn(), results(), 1)
    assert [c.id for c in second] == ["details:vue-dev", "details:react-dev"]
    third = recruiter.next_calls(turn(), results(), 2)
    assert [c.name for c in third] == ["packages.propose", "packages.install"]
    assert [p["name"] for p in third[0].args["proposals"]] == ["vue-dev", "react-dev"]
    assert third[1].args == {"name": "vue-dev", "version": "1.0.0"}
    assert recruiter.next_calls(turn(), results(), 3) == []


def test_output_lists_proposals_installed_and_flagged():
    installed = json.dumps({"status": "installed"})
    flagged = json.dumps(details("evil-dev", flags=["ignore_instructions"]))
    data = recruiter.output(
        turn(), results(**{"install:vue-dev": installed, "details:evil-dev": flagged})
    )["artifacts"][0]["data"]
    assert data["marketplace_status"] == "reachable"
    assert [(p["name"], p["for_tasks"]) for p in data["proposals"]] == [
        ("vue-dev", ["T-02"]),
        ("react-dev", ["T-01"]),
    ]
    assert data["proposals"][0]["permissions"] == [{"id": "project.tasks", "risk": "low"}]
    assert (data["proposals"][0]["rating"], data["proposals"][0]["installs"]) == (None, None)
    assert data["installed"] == ["vue-dev@1.0.0"]
    assert "Ignored instructions found in the README of evil-dev" in data["summary"]


def test_weak_candidates_are_dropped_and_tasks_limit_proposals():
    unknown = details("react-dev", permissions=[{"id": "browser.open", "risk": None}])
    data = recruiter.output(
        turn(task_ids=["T-01"]),
        results(**{"details:react-dev": json.dumps(unknown)}),
    )["artifacts"][0]["data"]
    assert [p["name"] for p in data["proposals"]] == ["vue-dev"]
    assert "installed" not in data
    supervised = recruiter.next_calls(turn(tools=ALL_TOOLS - {"packages.install"}), results(), 2)
    assert [c.name for c in supervised] == ["packages.propose"]


def test_unreachable_marketplace_and_missing_tools():
    unreachable = {"search": json.dumps({"source": "unreachable", "results": []})}
    data = recruiter.output(turn(), unreachable)["artifacts"][0]["data"]
    assert (data["marketplace_status"], data["proposals"]) == ("unreachable", [])
    assert recruiter.next_calls(turn(), unreachable, 1) == []
    assert recruiter.next_calls(turn(tools={"skills.read"}), {}, 0)[0].name == "skills.read"
    no_tools = recruiter.output(turn(tools=set()), {})["artifacts"][0]["data"]
    assert no_tools["marketplace_status"] == "unreachable"
    degraded = {"search": json.dumps({**SEARCH, "source": "cache"}), "details:vue-dev": "oops"}
    data = recruiter.output(turn(), degraded)["artifacts"][0]["data"]
    assert (data["marketplace_status"], data["proposals"]) == ("degraded", [])


def test_scripted_hire_without_candidates_keeps_the_canned_proposal():
    data = recruiter.output(turn(script={"hire": True}), {})["artifacts"][0]["data"]
    assert [p["name"] for p in data["proposals"]] == ["htmx-frontend-developer"]
