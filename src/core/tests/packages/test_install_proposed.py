# SPDX-License-Identifier: AGPL-3.0-or-later
"""System action `install_proposed_packages` after `approve_plan`, then `hire`."""

import pytest

from dexterhouse.apps.agents.models import AgentInstance
from dexterhouse.apps.events.models import Event
from dexterhouse.apps.projects.models import Artifact
from dexterhouse.apps.workflows import actions

from .conftest import index_entry, sha_of

pytestmark = pytest.mark.django_db
REPO = "https://github.com/janedoe/dh-security-reviewer"


def proposal(name="security-reviewer", version="1.0.0", **extra):
    return {
        "name": name,
        "version": version,
        "role": "security_reviewer",
        "reason": "OWASP review",
        "for_tasks": ["T-01"],
        "permissions": [{"id": "memory.search", "risk": "low"}],
        "risk": "low",
        "verified": True,
        "rating": 4.5,
        "installs": 10,
        "author_github": "janedoe",
        **extra,
    }


@pytest.fixture
def phase_run(project):
    from dexterhouse.apps.workflows.models import PhaseRun, ProcessRun

    run = ProcessRun.objects.create(
        project=project, process_name="p", process_version="1.0.0", definition={}
    )
    return PhaseRun.objects.create(process_run=run, phase_id="planning", position=0, room="x")


def propose(project, *proposals):
    Artifact.objects.create(
        project=project,
        kind="team_proposal",
        name="team_proposal.json",
        version=1,
        data={"proposals": list(proposals)},
        content_hash="0" * 64,
    )


def test_installs_then_hires_the_proposed_package(
    project, phase_run, pkg_dir, fake_git, index_file
):
    src = pkg_dir()
    fake_git[REPO] = src
    index_file(index_entry("security-reviewer", REPO, [("1.0.0", "v1.0.0", sha_of(src))]))
    propose(project, proposal(), proposal(name="ghost-agent"))
    result = actions.install_proposed_packages(project, phase_run)
    assert result.data["installed"] == ["security-reviewer@1.0.0"]
    assert "ghost-agent@1.0.0" in result.data["failed"]
    installed = Event.objects.get(type="package.installed", project_id=project.id)
    assert installed.payload["roles"] == ["security_reviewer"]
    hired = actions.hire(project, phase_run)
    assert hired.data["hired"] == ["security_reviewer"]
    agent = AgentInstance.objects.get(project=project, role="security_reviewer")
    assert agent.installed_version.package.name == "security-reviewer"
    assert agent.source == "marketplace"
    again = actions.install_proposed_packages(project, phase_run)
    assert again.data["skipped"] == ["security-reviewer@1.0.0"]
