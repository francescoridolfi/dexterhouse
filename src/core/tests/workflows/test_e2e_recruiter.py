# SPDX-License-Identifier: AGPL-3.0-or-later
"""Done criterion of E-08: the Recruiter searches a real registry, proposes, and the
process installs and hires after `approve_plan`, then the PM re-plans (both modes), or the
team stays built-in when the marketplace is unreachable.

The registry is a `file://` index; the packages are local bare git repositories reached
through `PACKAGES_GIT_MIRRORS`, their files through a `file://` `MARKETPLACE_RAW_URL`.
The tool server process of each turn gets the same settings from the `DH_TEST_*`
variables (settings/test.py).
"""

import json
import shutil
from pathlib import Path

import pytest

from dexterhouse.apps.agents.models import AgentInstance, AgentTurn, ToolCall
from dexterhouse.apps.packages.models import Package
from dexterhouse.apps.packages.services import index as registry
from dexterhouse.apps.packages.services import shared_cache
from dexterhouse.apps.workflows.models import StepRun
from tests.packages.conftest import git_repo, index_entry, write_package
from tests.packages.marketplace_fixtures import agent_definition
from tests.packages.test_git import archive_sha
from tests.workflows.conftest import drain, event_types, events, open_gate
from tests.workflows.test_e2e import create, decide

pytestmark = [
    pytest.mark.slow,  # whole processes, one MCP process per turn, real git
    pytest.mark.django_db(transaction=True),
    pytest.mark.usefixtures("builtin_runtime"),
]
PUBLIC = "https://github.com/dh-test/"
SPECIALISTS = {
    "vue-frontend-developer": {"verified": True, "tools": ["project.tasks", "skills.read"]},
    "react-frontend-developer": {"verified": False, "tools": ["project.tasks"]},
}


def _publish(root: Path) -> dict:
    """Two agent packages at v1.3.0: bare repositories, raw files and index entries."""
    entries = []
    for name, spec in SPECIALISTS.items():
        role = name.replace("-", "_")
        src = write_package(
            root / "src" / name,
            name,
            version="1.3.0",
            definition=agent_definition(role, spec["tools"]),
        )
        repo = git_repo(root / "repos" / name, src, "v1.3.0")
        shutil.copytree(src, root / "raw" / "dh-test" / name / "v1.3.0")
        sha = archive_sha(repo, "v1.3.0")
        entry = index_entry(
            name, PUBLIC + name, [("1.3.0", "v1.3.0", sha)], verified=spec["verified"]
        )
        entries.append({**entry, "tags": ["frontend"], "description": f"{role} specialist"})
    return {
        "schema": 1,
        "generated_at": "2026-11-01T10:00:00Z",
        "core_latest": "0.1.0",
        "packages": entries,
    }


@pytest.fixture
def marketplace(tmp_path, settings, monkeypatch):
    """Point this process and the tool servers at the test registry."""
    index = tmp_path / "registry" / "index.json"
    index.parent.mkdir()
    index.write_text(json.dumps(_publish(tmp_path)))
    values = {
        "REGISTRY_INDEX_URL": index.as_uri(),
        "PACKAGES_GIT_MIRRORS": {PUBLIC: (tmp_path / "repos").as_uri() + "/"},
        "MARKETPLACE_RAW_URL": (tmp_path / "raw").as_uri() + "/{path}/{ref}/{file}",
    }
    for name, value in values.items():
        setattr(settings, name, value)
        monkeypatch.setenv(
            f"DH_TEST_{name}", value if isinstance(value, str) else json.dumps(value)
        )
    monkeypatch.setenv("DH_TEST_PACKAGES_DIR", str(settings.PACKAGES_DIR))
    settings.AGENTS_DEMO_SCRIPT = {"tasks": 2}
    registry.clear_cache()
    shared_cache.clear()
    yield index
    registry.clear_cache()
    shared_cache.clear()


def recruiter_turn(project) -> AgentTurn:
    return AgentTurn.objects.get(project=project, agent_instance__role="recruiter")


def tools_called(project) -> list[str]:
    calls = ToolCall.objects.filter(agent_turn=recruiter_turn(project)).order_by("seq")
    return [c.tool for c in calls]


def run_to_completion(client, project) -> list[str]:
    approvals = []
    for _ in range(20):
        drain(project)
        gate = open_gate(project)
        if gate is None:
            break
        approvals.append(gate.gate_id)
        if gate.type == "question":
            answers = [{"question_id": q["id"], "answer": "No"} for q in gate.payload["questions"]]
            decide(client, gate, answers=answers)
        else:
            if gate.gate_id == "approve_plan":
                approvals.append(gate.payload["team"])
            decide(client, gate, decision="approve")
    project.refresh_from_db()
    return approvals


def assert_hired(project, names: set[str]) -> None:
    hired = AgentInstance.objects.filter(project=project, source="marketplace")
    assert {a.package_name for a in hired} == names
    for agent in hired:
        (event,) = [
            e for e in events(project, "agent.hired") if e.payload["agent_id"] == str(agent.id)
        ]
        assert event.payload["package"] == {"name": agent.package_name, "version": "1.3.0"}
        assert (event.payload["source"], event.payload["room"]) == ("marketplace", "hr_office")
        assert event.payload["allowed_tools"] == sorted(SPECIALISTS[agent.package_name]["tools"])
        assert event.payload["avatar"]["model"] == "default"
    replan = StepRun.objects.get(project=project, step="replan")
    board = replan.agent_turn.output["artifacts"][0]["data"]
    roles = {t["assigned_role"] for t in board["tasks"]}
    assert {n.replace("-", "_") for n in names} <= roles


def test_supervised_recruiter_proposes_and_the_gate_installs_and_hires(client, marketplace):
    project = create(client, execution_mode="supervised")
    client.post(f"/api/v1/projects/{project.id}/start")
    approvals = run_to_completion(client, project)
    assert project.status == "completed", event_types(project)[-5:]
    team = next(a for a in approvals if isinstance(a, dict))
    assert team["marketplace_status"] == "reachable"
    proposed = {p["name"]: p for p in team["proposals"]}
    assert set(proposed) == set(SPECIALISTS)
    assert proposed["vue-frontend-developer"]["permissions"] == [
        {"id": "project.tasks", "risk": "low"},
        {"id": "skills.read", "risk": "low"},
    ]
    assert (proposed["react-frontend-developer"]["verified"], team["installed"]) == (False, [])
    called = tools_called(project)
    assert called.count("marketplace.details") == 2
    assert "packages.propose" in called
    assert "packages.install" not in called
    offered = {t["name"] for t in recruiter_turn(project).tool_specs}
    assert "packages.install" not in offered
    assert_hired(project, set(SPECIALISTS))


def test_autonomous_recruiter_installs_only_verified_low_risk(client, marketplace):
    project = create(client, execution_mode="autonomous")
    client.post(f"/api/v1/projects/{project.id}/start")
    drain(project)
    project.refresh_from_db()
    assert project.status == "completed", event_types(project)[-5:]
    install = ToolCall.objects.get(agent_turn=recruiter_turn(project), tool="packages.install")
    assert install.arguments == {"name": "vue-frontend-developer", "version": "1.3.0"}
    assert '"status": "installed"' in install.result["content"]
    output = recruiter_turn(project).output["artifacts"][0]["data"]
    assert output["installed"] == ["vue-frontend-developer@1.3.0"]
    assert len(output["proposals"]) == 2
    assert not Package.objects.filter(name="react-frontend-developer").exists()
    assert_hired(project, {"vue-frontend-developer"})


def test_unreachable_marketplace_keeps_the_builtin_team(client, marketplace, settings, monkeypatch):
    missing = marketplace.parent / "gone.json"
    settings.REGISTRY_INDEX_URL = missing.as_uri()
    monkeypatch.setenv("DH_TEST_REGISTRY_INDEX_URL", missing.as_uri())
    (Path(settings.PACKAGES_DIR) / ".registry" / "index.json").unlink(missing_ok=True)
    registry.clear_cache()
    project = create(client, execution_mode="autonomous")
    client.post(f"/api/v1/projects/{project.id}/start")
    drain(project)
    project.refresh_from_db()
    assert project.status == "completed", event_types(project)[-5:]
    output = recruiter_turn(project).output["artifacts"][0]["data"]
    assert (output["marketplace_status"], output["proposals"]) == ("unreachable", [])
    assert "Marketplace unreachable" in recruiter_turn(project).inputs["step_description"]
    assert not AgentInstance.objects.filter(project=project, source="marketplace").exists()
    assert not StepRun.objects.filter(project=project, step="replan").exists()
