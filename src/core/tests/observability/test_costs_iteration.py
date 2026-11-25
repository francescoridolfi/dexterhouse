# SPDX-License-Identifier: AGPL-3.0-or-later
"""Costs per iteration: the brief (0) and each change request (n)."""

import pytest

from dexterhouse.apps.agents.models import AgentInstance, AgentTurn
from dexterhouse.apps.workflows.models import PhaseRun, ProcessRun

pytestmark = pytest.mark.django_db


def turn(project, row) -> AgentTurn:
    return AgentTurn.objects.create(
        organization_id=project.organization_id,
        project=project,
        agent_instance=AgentInstance.objects.filter(project=project).first(),
        phase_run=row,
        purpose="test",
    )


def test_costs_filter_by_iteration(client, started, make_call):
    project = started()
    first = PhaseRun.objects.get(process_run=project.current_run, phase_id="analysis")
    run = ProcessRun.objects.create(
        project=project, iteration=1, process_name="p", process_version="1", definition={}
    )
    second = PhaseRun.objects.create(process_run=run, phase_id="analysis", position=0, room="x")
    make_call(project, "0.4", agent_turn=turn(project, first))
    make_call(project, "0.1", agent_turn=turn(project, second))
    url = f"/api/v1/projects/{project.id}/costs"
    body = client.get(url).json()
    assert body["iteration"] is None
    assert body["by_iteration"] == [
        {"iteration": 0, "label": "brief", "cost": "0.400000"},
        {"iteration": 1, "label": "CR-1", "cost": "0.100000"},
    ]
    assert len(body["by_phase"]) == 2
    only = client.get(url, {"iteration": 1}).json()
    assert only["iteration"] == 1
    assert [p["phase_run"] for p in only["by_phase"]] == [str(second.id)]
    assert [p["cost"] for p in only["by_provider"]] == ["0.100000"]
    assert [d["cost"] for d in only["by_day"]] == ["0.100000"]
    assert client.get(url, {"iteration": "x"}).status_code == 400
