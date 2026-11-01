# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration E-02/E-03: LLMCall.project/agent_turn and ModelProfile.project become FKs."""

import django.db.models.deletion
from django.db import migrations, models

from dexterhouse.common.migrations import drop_orphans, uuid_to_fk

PROJECT = "projects.Project"


class Migration(migrations.Migration):
    dependencies = [
        ("gateway", "0002_model_profile_and_idempotency"),
        ("projects", "0002_initial"),
        ("agents", "0002_integration_foreign_keys"),
    ]

    operations = [
        drop_orphans("gateway.LLMCall", "project_id", PROJECT, nullable=False),
        drop_orphans("gateway.LLMCall", "agent_turn_id", "agents.AgentTurn", nullable=True),
        drop_orphans("gateway.ModelProfile", "project_id", PROJECT, nullable=False),
        migrations.RemoveIndex("llmcall", "dh_llmcall_project_created"),
        migrations.RemoveIndex("llmcall", "dh_llmcall_turn"),
        migrations.RemoveConstraint("modelprofile", "dh_modelprofile_org_unique"),
        migrations.RemoveConstraint("modelprofile", "dh_modelprofile_project_unique"),
        *uuid_to_fk(
            "llmcall",
            "project_id",
            "project",
            models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="llm_calls",
                to="projects.project",
            ),
        ),
        *uuid_to_fk(
            "llmcall",
            "agent_turn_id",
            "agent_turn",
            models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="llm_calls",
                to="agents.agentturn",
            ),
        ),
        *uuid_to_fk(
            "modelprofile",
            "project_id",
            "project",
            models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="model_profiles",
                to="projects.project",
            ),
        ),
        migrations.AddIndex(
            "llmcall",
            models.Index(fields=["project", "created_at"], name="dh_llmcall_project_created"),
        ),
        migrations.AddIndex("llmcall", models.Index(fields=["agent_turn"], name="dh_llmcall_turn")),
        migrations.AddConstraint(
            "modelprofile",
            models.UniqueConstraint(
                condition=models.Q(project__isnull=True),
                fields=("organization", "profile"),
                name="dh_modelprofile_org_unique",
            ),
        ),
        migrations.AddConstraint(
            "modelprofile",
            models.UniqueConstraint(
                condition=models.Q(project__isnull=False),
                fields=("organization", "project", "profile"),
                name="dh_modelprofile_project_unique",
            ),
        ),
    ]
