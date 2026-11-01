# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration E-02/E-03: project, phase run, task and step run become foreign keys."""

import django.db.models.deletion
from django.db import migrations, models

from dexterhouse.common.migrations import drop_orphans, uuid_to_fk

PROJECT = "projects.Project"


class Migration(migrations.Migration):
    dependencies = [
        ("agents", "0001_initial"),
        ("projects", "0002_initial"),
        ("workflows", "0001_initial"),
    ]

    operations = [
        drop_orphans("agents.AgentTurn", "project_id", PROJECT, nullable=False),
        drop_orphans("agents.AgentInstance", "project_id", PROJECT, nullable=False),
        drop_orphans("agents.AgentTurn", "phase_run_id", "workflows.PhaseRun", nullable=True),
        drop_orphans("agents.AgentTurn", "task_id", "workflows.Task", nullable=True),
        drop_orphans("agents.AgentTurn", "step_run_id", "workflows.StepRun", nullable=True),
        migrations.RemoveIndex("agentinstance", "dh_agent_project_role"),
        migrations.RemoveIndex("agentturn", "dh_turn_project_created"),
        migrations.RemoveConstraint("agentturn", "dh_turn_step_run_attempt_unique"),
        *uuid_to_fk(
            "agentinstance",
            "project_id",
            "project",
            models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="agents",
                to="projects.project",
            ),
        ),
        *uuid_to_fk(
            "agentturn",
            "project_id",
            "project",
            models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="agent_turns",
                to="projects.project",
            ),
        ),
        *uuid_to_fk(
            "agentturn",
            "phase_run_id",
            "phase_run",
            models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="agent_turns",
                to="workflows.phaserun",
            ),
        ),
        *uuid_to_fk(
            "agentturn",
            "task_id",
            "task",
            models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="agent_turns",
                to="workflows.task",
            ),
        ),
        *uuid_to_fk(
            "agentturn",
            "step_run_id",
            "step_run",
            models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="agent_turns",
                to="workflows.steprun",
            ),
        ),
        migrations.AddIndex(
            "agentinstance",
            models.Index(fields=["project", "role"], name="dh_agent_project_role"),
        ),
        migrations.AddIndex(
            "agentturn",
            models.Index(fields=["project", "created_at"], name="dh_turn_project_created"),
        ),
        migrations.AddConstraint(
            "agentturn",
            models.UniqueConstraint(
                condition=models.Q(step_run__isnull=False),
                fields=("step_run", "step_attempt"),
                name="dh_turn_step_run_attempt_unique",
            ),
        ),
    ]
