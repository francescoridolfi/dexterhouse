# SPDX-License-Identifier: AGPL-3.0-or-later
"""The team of a project: packages by role or name, hiring, placeholders."""

import shutil

import pytest

from dexterhouse.apps.agents.models import AgentInstance
from dexterhouse.apps.agents.services import roster
from dexterhouse.apps.events.models import Event
from tests.conftest import TEAM_PACKAGES

pytestmark = pytest.mark.django_db
PROPOSAL = {
    "name": "htmx-frontend-developer",
    "version": "1.3.0",
    "role": "htmx_frontend_developer",
    "permissions": [{"id": "project.tasks", "risk": "low"}],
}


def test_packages_are_found_in_order_and_invalid_ones_skipped(settings, tmp_path):
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "agent.yaml").write_text("schema: 1\n")
    settings.AGENTS_PACKAGE_DIRS = [str(tmp_path / "missing"), str(tmp_path), str(TEAM_PACKAGES)]
    assert roster.find_package(role="tester").name == "tester"
    assert roster.find_package(name="htmx-frontend-developer").agent.role == (
        "htmx_frontend_developer"
    )
    assert roster.find_package(role="designer") is None
    assert "htmx_frontend_developer" in roster.installed_package_roles()


def test_ensure_agent_hires_once_and_replaces_a_released_one(project, team_packages):
    first = roster.ensure_agent(project, "reviewer")
    assert first.id == roster.team_agent_id(project.id, "reviewer")
    assert (first.source, first.room) == ("local", "review_corner")
    assert roster.ensure_agent(project, "reviewer") == first
    first.status = "released"
    first.save()
    second = roster.ensure_agent(project, "reviewer")
    assert second.id != first.id
    assert roster.active_agent(project.id, "reviewer") == second


def test_placeholder_without_package(project):
    agent = roster.ensure_agent(project, "project_manager", room="pm_office")
    assert (agent.package_name, agent.package_path, agent.room) == (
        "placeholder-project-manager",
        "",
        "pm_office",
    )
    hired = Event.objects.get(type="agent.hired")
    assert hired.payload["package"] == {"name": "placeholder-project-manager", "version": "0.0.0"}


def test_builtin_source(project, settings, tmp_path):
    settings.BUILTIN_DIR = str(tmp_path)
    shutil.copytree(TEAM_PACKAGES / "tester", tmp_path / "agents" / "tester")
    settings.AGENTS_PACKAGE_DIRS = [str(tmp_path / "agents")]
    assert roster.ensure_agent(project, "tester").source == "builtin"


def test_hire_proposed_grants_the_proposal_permissions(project, team_packages):
    hired = roster.hire_proposed(project, [PROPOSAL, {**PROPOSAL, "name": "ghost", "role": "x"}])
    assert [a.role for a in hired] == ["htmx_frontend_developer"]
    assert hired[0].allowed_tools == ["project.tasks"]  # workspace.write was not granted
    again = roster.hire_proposed(project, [PROPOSAL])
    assert again == hired
    assert AgentInstance.objects.filter(project=project).count() == 1
