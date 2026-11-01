# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration E-02/E-03: MemoryChunk.project becomes a foreign key to Project."""

import django.db.models.deletion
from django.db import migrations, models

from dexterhouse.common.migrations import drop_orphans, uuid_to_fk


class Migration(migrations.Migration):
    dependencies = [
        ("memory", "0001_initial"),
        ("projects", "0002_initial"),
    ]

    operations = [
        drop_orphans("memory.MemoryChunk", "project_id", "projects.Project", nullable=False),
        migrations.RemoveIndex("memorychunk", "dh_memory_project_kind"),
        *uuid_to_fk(
            "memorychunk",
            "project_id",
            "project",
            models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="memory_chunks",
                to="projects.project",
            ),
        ),
        migrations.AddIndex(
            "memorychunk",
            models.Index(fields=["project", "kind"], name="dh_memory_project_kind"),
        ),
    ]
