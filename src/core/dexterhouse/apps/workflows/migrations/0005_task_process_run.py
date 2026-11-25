# SPDX-License-Identifier: AGPL-3.0-or-later

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import OuterRef, Subquery


def backfill(apps, schema_editor):
    """Every task belongs to the run of its phase run (one run per project before E-13)."""
    Task = apps.get_model("workflows", "Task")
    PhaseRun = apps.get_model("workflows", "PhaseRun")
    run = PhaseRun.objects.filter(pk=OuterRef("phase_run_id")).values("process_run_id")
    Task.objects.filter(process_run__isnull=True).update(process_run=Subquery(run[:1]))


class Migration(migrations.Migration):
    dependencies = [
        ("agents", "0003_agentinstance_installed_version"),
        ("projects", "0005_context_kind"),
        ("workflows", "0004_process_run_iterations"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="process_run",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="tasks",
                to="workflows.processrun",
            ),
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="task",
            constraint=models.UniqueConstraint(
                condition=models.Q(("parent__isnull", True)),
                fields=("process_run", "external_id"),
                name="dh_task_run_external_unique",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="task",
            name="dh_task_external_unique",
        ),
    ]
