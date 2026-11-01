# SPDX-License-Identifier: AGPL-3.0-or-later
"""The integration migrations keep E-02/E-03 rows: uuid columns become FKs in place."""

import uuid

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [
    ("agents", "0001_initial"),
    ("workflows", "0001_initial"),
    ("projects", "0002_initial"),
    ("gateway", "0002_model_profile_and_idempotency"),
    ("memory", "0001_initial"),
]
AFTER = [
    ("agents", "0002_integration_foreign_keys"),
    ("workflows", "0002_integration_foreign_keys"),
    ("projects", "0003_artifact_produced_by_turn"),
    ("gateway", "0003_integration_foreign_keys"),
    ("memory", "0002_memorychunk_project"),
    ("observability", "0001_initial"),  # depends on projects: re-applied after the rollback
]
NAMESPACE = uuid.UUID("5f0c8a52-4c1e-4d7e-9b2a-6d8e0f3a7c10")


def migrate(targets):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)
    return executor.loader.project_state(targets).apps


@pytest.mark.django_db(transaction=True)
def test_e02_rows_get_placeholder_agents_and_orphans_are_dropped(organization, user):
    apps = migrate(BEFORE)
    Project = apps.get_model("projects", "Project")
    project = Project.objects.create(
        organization_id=organization.id,
        name="Old",
        slug="old",
        brief="b",
        process_name="software-house-default",
        process_version="1.0.0",
        budget=1,
        created_by_id=user.id,
    )
    run = apps.get_model("workflows", "ProcessRun").objects.create(
        project=project, process_name="p", process_version="1", definition={}
    )
    phase = apps.get_model("workflows", "PhaseRun").objects.create(
        process_run=run, phase_id="analysis", position=0, room="meeting_room"
    )
    agent_id = uuid.uuid5(NAMESPACE, f"{project.id}:analyst")
    apps.get_model("workflows", "StepRun").objects.create(
        project=project, phase_run=phase, seq=1, step_index=0, step="analyst", role="analyst",
        agent_id=agent_id,
    )  # fmt: skip
    apps.get_model("gateway", "LLMCall").objects.create(
        organization_id=organization.id, project_id=uuid.uuid4(), provider="fake", model="m",
        profile="fast", status="ok",
    )  # fmt: skip

    apps = migrate(AFTER)
    agent = apps.get_model("agents", "AgentInstance").objects.get(pk=agent_id)
    assert (agent.role, agent.package_path, agent.project_id) == ("analyst", "", project.id)
    assert apps.get_model("workflows", "StepRun").objects.get().agent_id == agent_id
    assert not apps.get_model("gateway", "LLMCall").objects.exists()  # orphan dropped
