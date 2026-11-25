# SPDX-License-Identifier: AGPL-3.0-or-later

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0005_context_kind"),
        ("workflows", "0003_gate_reminders"),
    ]

    operations = [
        migrations.AddField(
            model_name="processrun",
            name="iteration",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="processrun",
            name="project",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="process_runs",
                to="projects.project",
            ),
        ),
        migrations.AddConstraint(
            model_name="processrun",
            constraint=models.UniqueConstraint(
                fields=("project", "iteration"), name="dh_processrun_iteration_unique"
            ),
        ),
    ]
