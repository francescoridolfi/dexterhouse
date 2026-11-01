# SPDX-License-Identifier: AGPL-3.0-or-later
"""The built-in agent packages (F-002): valid, complete and consistent with the processes."""

import re
from pathlib import Path

import pytest
import yaml
from django.conf import settings

from dexterhouse.apps.agents.schemas import TurnInputs
from dexterhouse.apps.agents.services.context import BUDGETS, ContextRequest, build_context
from dexterhouse.apps.agents.services.packages import load_agent_package
from dexterhouse.apps.workflows.roles import BUILTIN_ROLES, ROLE_ROOMS
from dexterhouse_schema import Process
from dexterhouse_schema.package import validate_package
from dexterhouse_schema.report import ValidationReport
from dexterhouse_schema.skill_check import validate_skill_dir

ROLES = sorted(BUILTIN_ROLES)
SECTIONS = ["Role", "Inputs", "Output contract", "Constraints", "Quality bar", "Working method"]
REMINDER = (
    "If you cannot complete the contract, return status `blocked` with a reason; "
    "never fabricate results of tools you did not call."
)
#: theme.md, "Ruoli built-in".
COLORS = {
    "analyst": "#7DB7E7",
    "architect": "#B48CE7",
    "project_manager": "#E7D77D",
    "recruiter": "#E79D7D",
    "developer": "#7DE7B8",
    "reviewer": "#7D9CE7",
    "tester": "#E77DA6",
}
WRITE_TOOLS = {"workspace.write", "workspace.edit", "workspace.delete", "workspace.move"}


def builtin() -> Path:
    return Path(settings.BUILTIN_DIR)


def package_dir(role: str) -> Path:
    return builtin() / "agents" / role.replace("_", "-")


def package(role: str):
    return load_agent_package(package_dir(role))


def test_one_package_per_builtin_role():
    on_disk = {p.parent.name for p in (builtin() / "agents").glob("*/agent.yaml")}
    assert on_disk == {r.replace("_", "-") for r in ROLES}


@pytest.mark.parametrize("role", ROLES)
def test_package_is_valid_and_complete(role):
    report = validate_package(package_dir(role))
    assert report.errors == []
    assert report.warnings == []
    agent = package(role).agent
    assert agent.role == role
    assert agent.skills, "at least one role skill"
    assert agent.office.room == ROLE_ROOMS[role]
    assert agent.office.color == COLORS[role]
    assert agent.office.avatar
    assert (package_dir(role) / agent.office.avatar).is_file()
    assert "git.push" not in agent.tools  # CD-039: pushing is a system action


@pytest.mark.parametrize("role", ROLES)
def test_system_prompt_follows_the_conventions(role):
    text = package(role).system_prompt
    headings = re.findall(r"^# (.+)$", text, flags=re.MULTILINE)
    assert headings == SECTIONS
    assert text.rstrip().endswith(REMINDER)
    assert not re.search(r"/Users/|/home/|C:\\\\|sk-[A-Za-z0-9]{8}", text)
    contract = text.split("# Output contract", 1)[1].split("# Constraints", 1)[0]
    for kind in package(role).agent.output_contract.artifacts:
        assert kind in contract, f"{kind} not described in the output contract"


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("profile", ["strong", "balanced"])
def test_prefix_fits_the_context_budget(role, profile):
    pkg = package(role)
    built = build_context(
        ContextRequest(
            package=pkg,
            inputs=TurnInputs(may_ask=True),
            profile=profile,
            tools=[],
            allowed_tools=frozenset(pkg.agent.tools),
        )
    )
    assert built.manifest["prefix_tokens"] <= 0.25 * BUDGETS[profile].cap
    assert built.manifest["truncations"] == []


def test_output_contracts_cover_what_the_processes_ask():
    for path in (builtin() / "processes").glob("*/process.yaml"):
        process = Process.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        for phase in process.phases:
            for step in [*phase.step_list(), *phase.after_gate]:
                produces = set(step.produces) or (set(phase.produces) if phase.agent else set())
                contract = set(package(step.agent).agent.output_contract.artifacts)
                assert produces <= contract, (path.parent.name, phase.id, step.agent)
    assert {"questions", "assumptions"} <= set(package("analyst").agent.output_contract.artifacts)
    assert package("reviewer").agent.output_contract.output_schema == "review"
    assert package("tester").agent.output_contract.output_schema == "test_report"
    assert package("architect").agent.output_contract.output_schema == "stack"


def test_permissions_follow_the_role_cards():
    assert not WRITE_TOOLS & set(package("reviewer").agent.tools)
    assert not {"git.add", "git.commit"} & set(package("reviewer").agent.tools)
    assert package("analyst").agent.capabilities.may_ask
    assert "project.ask" in package("analyst").agent.tools
    assert "packages.install" in package("recruiter").agent.tools  # autonomous mode only
    assert "workspace.run_tests" in package("tester").agent.tools


def _allowed(policy: dict, path: str) -> bool:
    return re.search(policy["path"]["pattern"], path) is not None


@pytest.mark.parametrize(
    ("path", "tester", "developer"),
    [
        ("tests/acceptance/test_t05.py", True, False),
        ("tests/test_models.py", True, True),
        ("bookings/test_services.py", True, True),
        ("web/src/booking.test.ts", True, True),
        ("web/src/booking.spec.js", True, True),
        ("bookings/conftest.py", True, True),
        ("bookings/models.py", False, True),
        ("README.md", False, True),
        ("tests/../bookings/models.py", False, False),
    ],
)
def test_test_paths_split_tester_and_developer(path, tester, developer):
    """CD-032: the tester writes only tests; the developer leaves acceptance tests alone."""
    tester_policy = package("tester").agent.args_policy
    developer_policy = package("developer").agent.args_policy
    assert set(tester_policy) == {"workspace.write", "workspace.edit"}
    assert all(_allowed(tester_policy[t], path) == tester for t in tester_policy)
    for tool in ("workspace.write", "workspace.edit", "workspace.delete", "git.checkout_file"):
        assert _allowed(developer_policy[tool], path) == developer
    move = developer_policy["workspace.move"]
    assert (re.search(move["to"]["pattern"], path) is not None) == developer


def test_shared_skills_are_valid():
    folders = sorted((builtin() / "skills").iterdir())
    assert {f.name for f in folders} >= {"conventional-commits", "markdown-artifacts"}
    for folder in folders:
        report = ValidationReport()
        validate_skill_dir(folder, f"skills/{folder.name}", report)
        assert report.errors == [], folder.name
    role_skills = {s for r in ROLES for s in package(r).agent.skills}
    assert not role_skills & {f.name for f in folders}, "a role skill shadows a shared one"
