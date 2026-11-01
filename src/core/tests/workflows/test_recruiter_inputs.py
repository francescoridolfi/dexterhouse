# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the Recruiter is told about the marketplace, and the gate's view of its proposal."""

import json

import pytest

from dexterhouse.apps.packages.services import index as registry
from dexterhouse.apps.packages.services import shared_cache
from dexterhouse.apps.projects.models import Artifact
from dexterhouse.apps.workflows import proposals
from dexterhouse.apps.workflows.models import PhaseRun, ProcessRun
from dexterhouse.apps.workflows.runners.inputs import _marketplace_line
from tests.packages.conftest import index_entry

pytestmark = pytest.mark.django_db


@pytest.fixture
def index(settings, tmp_path):
    def write(*entries):
        path = tmp_path / "index.json"
        body = {"schema": 1, "generated_at": "2026-11-01T10:00:00Z", "core_latest": "0.1.0"}
        path.write_text(json.dumps({**body, "packages": list(entries)}))
        settings.REGISTRY_INDEX_URL = path.as_uri()
        registry.clear_cache()
        shared_cache.clear()

    yield write
    registry.clear_cache()


def entry(name, **extra):
    return index_entry(
        name, f"https://github.com/x/{name}", [("1.0.0", "v1.0.0", "0" * 64)], **extra
    )


def test_the_recruiter_is_told_whether_the_marketplace_answers(index, settings):
    assert _marketplace_line().startswith("Marketplace unreachable (no registry configured")
    index(entry("alpha-agent"), entry("beta-agent"))
    assert _marketplace_line() == (
        "Marketplace reachable (source index, 2 packages; ratings and installs are not "
        "published yet)."
    )


def test_only_verified_low_risk_entries_install_without_a_person(index):
    index(
        entry("good", verified=True),
        entry("unverified"),
        entry("risky", verified=True, risk="medium"),
    )
    assert proposals.installs_without_gate({"name": "good"})
    assert not proposals.installs_without_gate({"name": "unverified"})
    assert not proposals.installs_without_gate({"name": "risky"})
    assert not proposals.installs_without_gate({"name": "ghost"})


def test_gate_team_reads_the_phase_proposal(project):
    run = ProcessRun.objects.create(
        project=project, process_name="p", process_version="1", definition={}
    )
    row = PhaseRun.objects.create(process_run=run, phase_id="planning", position=0, room="x")
    assert proposals.gate_team(row) is None
    proposal = {"name": "n", "version": "1.0.0", "role": "r", "for_tasks": ["T-01"], "extra": 1}
    Artifact.objects.create(
        project=project,
        phase_run=row,
        kind="team_proposal",
        name="team_proposal.json",
        version=1,
        data={"marketplace_status": "degraded", "proposals": [proposal], "summary": "s"},
        content_hash="0" * 64,
    )
    team = proposals.gate_team(row)
    assert (team["marketplace_status"], team["summary"], team["installed"]) == ("degraded", "s", [])
    assert team["proposals"][0]["name"] == "n"
    assert "extra" not in team["proposals"][0]
    assert proposals.proposals(project) == [proposal]
