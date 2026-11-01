# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration E-02/E-03: Artifact.produced_by_turn becomes a foreign key to AgentTurn."""

import django.db.models.deletion
from django.db import migrations, models

from dexterhouse.common.migrations import drop_orphans, uuid_to_fk


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0002_initial"),
        ("agents", "0002_integration_foreign_keys"),
    ]

    operations = [
        drop_orphans("projects.Artifact", "produced_by_turn_id", "agents.AgentTurn", nullable=True),
        *uuid_to_fk(
            "artifact",
            "produced_by_turn_id",
            "produced_by_turn",
            models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="artifacts",
                to="agents.agentturn",
            ),
        ),
    ]
