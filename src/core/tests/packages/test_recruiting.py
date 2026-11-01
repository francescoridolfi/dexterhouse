# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Recruiter's `packages.*` tools as services (E-08)."""

import pytest

from dexterhouse.apps.packages.models import Package
from dexterhouse.apps.packages.services import recruiting
from dexterhouse.apps.projects.models import Artifact
from dexterhouse.apps.projects.services.tools import ToolError

from .conftest import index_entry, sha_of

pytestmark = pytest.mark.django_db
REPO = "https://github.com/janedoe/dh-security-reviewer"


@pytest.fixture
def ctx(project):
    Artifact.objects.create(
        project=project,
        kind="task_board",
        name="task_board.json",
        version=1,
        data={"tasks": [{"external_id": "T-01"}, {"external_id": "T-02"}]},
        content_hash="0" * 64,
    )
    return recruiting.RecruitingContext(project.id, project.organization_id)


def test_installed_lists_the_organization_packages(ctx):
    agents = recruiting.installed(ctx, "agent")["packages"]
    recruiter = next(p for p in agents if p["name"] == "recruiter")
    assert (recruiter["role"], recruiter["source"], recruiter["status"]) == (
        "recruiter",
        "builtin",
        "installed",
    )
    tools = {p["name"] for p in recruiting.installed(ctx, "tool")["packages"]}
    assert {"marketplace", "packages", "memory"} <= tools
    assert len(recruiting.installed(ctx)["packages"]) >= len(agents) + len(tools)
    with pytest.raises(ToolError, match="kind must be"):
        recruiting.installed(ctx, "theme")


def test_propose_checks_index_board_and_risk(ctx, publish):
    publish("htmx-frontend-developer", verified=True)
    publish("risky-agent", risk="high")
    publish("git-tools", kind="tool")
    good = {"name": "htmx-frontend-developer", "reason": "UI", "for_tasks": ["T-02"]}
    result = recruiting.propose(
        ctx,
        [
            good,
            {"name": "risky-agent", "reason": "x", "for_tasks": ["T-01"]},
            {"name": "git-tools", "version": "9.9.9", "reason": "", "for_tasks": ["T-09"]},
        ],
    )
    (recorded,) = result["recorded"]
    assert recorded == {
        "name": "htmx-frontend-developer",
        "version": "1.0.0",
        "reason": "UI",
        "for_tasks": ["T-02"],
        "verified": True,
        "risk": "low",
        "author_github": "janedoe",
        "rating": None,
        "installs": None,
    }
    problems = {r["name"]: r["problems"] for r in result["rejected"]}
    assert problems["risky-agent"] == ["risk high: cannot be proposed"]
    assert problems["git-tools"] == [
        "kind tool: only agent packages are proposed",
        "no such version compatible with this core",
        "for_tasks not in the task board: T-09",
        "reason is empty",
    ]
    ghost = recruiting.propose(ctx, [{"name": "ghost", "for_tasks": []}])
    assert ghost["rejected"] == [{"name": "ghost", "problems": ["not in the registry index"]}]
    with pytest.raises(ToolError, match="at most 3"):
        recruiting.propose(ctx, [good] * 4)
    with pytest.raises(ToolError, match="non-empty list"):
        recruiting.propose(ctx, [])


def test_install_requires_autonomous_mode_and_a_verified_low_risk_entry(
    ctx, project, pkg_dir, fake_git, index_file
):
    src = pkg_dir()
    fake_git[REPO] = src
    entry = index_entry("security-reviewer", REPO, [("1.0.0", "v1.0.0", sha_of(src))])
    index_file(entry)
    with pytest.raises(ToolError, match="requires_gate: packages are installed after"):
        recruiting.install(ctx, "security-reviewer")
    project.execution_mode = "autonomous"
    project.save(update_fields=["execution_mode"])
    with pytest.raises(ToolError, match="requires_gate: security-reviewer is not verified"):
        recruiting.install(ctx, "security-reviewer")
    with pytest.raises(ToolError, match="not in the registry index"):
        recruiting.install(ctx, "ghost")
    index_file({**entry, "verified": True})
    result = recruiting.install(ctx, "security-reviewer", "1.0.0")
    assert (result["status"], result["version"], result["errors"]) == ("installed", "1.0.0", [])
    package = Package.objects.get(name="security-reviewer")
    assert (package.organization_id, package.source) == (project.organization_id, "marketplace")


def test_unknown_project_is_refused(organization):
    import uuid

    ctx = recruiting.RecruitingContext(uuid.uuid4(), organization.id)
    with pytest.raises(ToolError, match="unknown project"):
        recruiting.install(ctx, "x")
