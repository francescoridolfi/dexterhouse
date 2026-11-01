# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration E-02/E-03: StepRun.agent/agent_turn and Task.assigned_instance become FKs.

E-02 wrote a placeholder `StepRun.agent_id = uuid5(project, role)` that events also carry;
each one becomes a placeholder `AgentInstance` with that id, so history stays consistent.
"""

import django.db.models.deletion
from django.db import migrations, models

from dexterhouse.common.migrations import drop_orphans, uuid_to_fk

ROOMS = {
    "analyst": "meeting_room",
    "architect": "design_studio",
    "project_manager": "pm_office",
    "recruiter": "hr_office",
    "developer": "open_space",
    "reviewer": "review_corner",
    "tester": "qa_lab",
}


def placeholder_agents(apps, schema_editor):
    StepRun = apps.get_model("workflows", "StepRun")
    AgentInstance = apps.get_model("agents", "AgentInstance")
    Project = apps.get_model("projects", "Project")
    known = set(AgentInstance.objects.values_list("id", flat=True))
    pairs = StepRun.objects.values_list("agent_id", "project_id", "role").distinct()
    for agent_id, project_id, role in pairs:
        if agent_id in known:
            continue
        project = Project.objects.get(pk=project_id)
        AgentInstance.objects.create(
            id=agent_id,
            organization_id=project.organization_id,
            project_id=project_id,
            package_name=f"placeholder-{role}"[:120],
            package_version="0.0.0",
            package_path="",
            role=role,
            display_name=role.replace("_", " ").title()[:80],
            model_profile="balanced",
            allowed_tools=[],
            room=ROOMS.get(role, "open_space"),
            avatar={"model": "default", "color": "#888888"},
            source="builtin",
        )
        known.add(agent_id)


class Migration(migrations.Migration):
    dependencies = [
        ("workflows", "0001_initial"),
        ("agents", "0002_integration_foreign_keys"),
    ]

    operations = [
        migrations.RunPython(placeholder_agents, migrations.RunPython.noop),
        drop_orphans("workflows.StepRun", "agent_turn_id", "agents.AgentTurn", nullable=True),
        drop_orphans(
            "workflows.Task", "assigned_instance_id", "agents.AgentInstance", nullable=True
        ),
        *uuid_to_fk(
            "steprun",
            "agent_id",
            "agent",
            models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="step_runs",
                to="agents.agentinstance",
            ),
        ),
        *uuid_to_fk(
            "steprun",
            "agent_turn_id",
            "agent_turn",
            models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="agents.agentturn",
            ),
        ),
        *uuid_to_fk(
            "task",
            "assigned_instance_id",
            "assigned_instance",
            models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="tasks",
                to="agents.agentinstance",
            ),
        ),
    ]
