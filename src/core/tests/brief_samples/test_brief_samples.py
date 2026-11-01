# SPDX-License-Identifier: AGPL-3.0-or-later
"""Brief samples (F-002): three briefs through `software-house-default` with the built-in
agents and the demo responder; structural assertions on every artifact, not on content."""

from pathlib import Path

import pytest
import yaml

from dexterhouse.apps.projects.models import Project
from tests.brief_samples import structure
from tests.conftest import TEAM_PACKAGES, install_test_packages
from tests.workflows.conftest import drain, event_types, open_gate

pytestmark = [
    pytest.mark.slow,  # whole software-house-default run per brief, real runtime and MCP processes
    pytest.mark.django_db(transaction=True),
    pytest.mark.usefixtures("builtin_runtime"),
]
BRIEFS = sorted((Path(__file__).parent / "briefs").glob("*.yaml"))


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def run(client, sample: dict) -> Project:
    """Create, start and drive the project through every gate (answers, approvals)."""
    body = {
        "name": sample["name"],
        "brief": sample["brief"],
        "budget": 20,
        "execution_mode": sample["execution_mode"],
    }
    response = client.post("/api/v1/projects", body, format="json")
    assert response.status_code == 201, response.json()
    project = Project.objects.get(pk=response.json()["id"])
    assert client.post(f"/api/v1/projects/{project.id}/start").status_code == 200
    for _ in range(30):
        drain(project)
        gate = open_gate(project)
        if gate is None:
            break
        if gate.type == "question":
            answers = [
                {"question_id": q["id"], "answer": (q.get("options") or ["Yes"])[0]}
                for q in gate.payload["questions"]
            ]
            decision = {"answers": answers}
        else:
            decision = {"decision": "approve"}
        result = client.post(f"/api/v1/gates/{gate.id}/decide", decision, format="json")
        assert result.status_code == 200, result.json()
    project.refresh_from_db()
    return project


@pytest.mark.parametrize("path", BRIEFS, ids=[p.stem for p in BRIEFS])
def test_brief_sample(client, settings, path):
    sample = load(path)
    settings.AGENTS_DEMO_SCRIPT = sample.get("script", {})
    if settings.AGENTS_DEMO_SCRIPT.get("hire"):  # the proposed specialist is installed
        install_test_packages(TEAM_PACKAGES)  # extra roles; the built-in team stays

    project = run(client, sample)

    assert project.status == "completed", event_types(project)[-8:]
    structure.assert_artifacts_are_well_formed(project)
    structure.assert_analysis(project)
    structure.assert_architecture(project)
    roles = {"analyst", "architect", "project_manager", "recruiter", "developer", "reviewer"}
    structure.assert_planning(project, roles | {"tester", "htmx_frontend_developer"})
    structure.assert_delivery(project)
    kinds = {a.kind for a in structure.latest(project).values()}
    if sample["execution_mode"] == "autonomous":
        assert "assumptions" in kinds
    else:
        assert "questions" in kinds
