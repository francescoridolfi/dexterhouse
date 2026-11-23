# SPDX-License-Identifier: AGPL-3.0-or-later

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import dexterhouse.common.models


class Migration(migrations.Migration):
    dependencies = [
        ("agents", "0003_agentinstance_installed_version"),
        ("projects", "0005_context_kind"),
        ("workflows", "0005_task_process_run"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ChangeRequest",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=dexterhouse.common.models.new_id,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("number", models.PositiveIntegerField()),
                ("title", models.CharField(max_length=120)),
                ("body", models.TextField(max_length=20000)),
                ("budget", models.DecimalField(decimal_places=6, default=0, max_digits=12)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("queued", "Queued"),
                            ("running", "Running"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="draft",
                        max_length=16,
                    ),
                ),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "dh_projects_changerequest",
                "ordering": ["number"],
            },
        ),
        migrations.RemoveConstraint(
            model_name="artifact",
            name="dh_artifact_kind_valid",
        ),
        migrations.AlterField(
            model_name="artifact",
            name="kind",
            field=models.CharField(
                choices=[
                    ("brief", "Brief"),
                    ("requirements", "Requirements"),
                    ("user_stories", "User Stories"),
                    ("questions", "Questions"),
                    ("assumptions", "Assumptions"),
                    ("architecture", "Architecture"),
                    ("adr", "Adr"),
                    ("stack", "Stack"),
                    ("task_board", "Task Board"),
                    ("team_proposal", "Team Proposal"),
                    ("dev_notes", "Dev Notes"),
                    ("review", "Review"),
                    ("test_report", "Test Report"),
                    ("release_notes", "Release Notes"),
                    ("retrospective", "Retrospective"),
                    ("code_graph", "Code Graph"),
                    ("context", "Context"),
                    ("change_request", "Change Request"),
                    ("file", "File"),
                ],
                max_length=32,
            ),
        ),
        migrations.AddConstraint(
            model_name="artifact",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "kind__in",
                        [
                            "brief",
                            "requirements",
                            "user_stories",
                            "questions",
                            "assumptions",
                            "architecture",
                            "adr",
                            "stack",
                            "task_board",
                            "team_proposal",
                            "dev_notes",
                            "review",
                            "test_report",
                            "release_notes",
                            "retrospective",
                            "code_graph",
                            "context",
                            "change_request",
                            "file",
                        ],
                    )
                ),
                name="dh_artifact_kind_valid",
            ),
        ),
        migrations.AddField(
            model_name="changerequest",
            name="created_by",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="change_requests",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="changerequest",
            name="process_run",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="change_request",
                to="workflows.processrun",
            ),
        ),
        migrations.AddField(
            model_name="changerequest",
            name="project",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="change_requests",
                to="projects.project",
            ),
        ),
        migrations.AddConstraint(
            model_name="changerequest",
            constraint=models.UniqueConstraint(
                fields=("project", "number"), name="dh_cr_number_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="changerequest",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "running")),
                fields=("project",),
                name="dh_cr_one_running",
            ),
        ),
        migrations.AddConstraint(
            model_name="changerequest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "status__in",
                        ["draft", "queued", "running", "completed", "failed", "cancelled"],
                    )
                ),
                name="dh_cr_status_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="changerequest",
            constraint=models.CheckConstraint(
                condition=models.Q(("budget__gte", 0)), name="dh_cr_budget_valid"
            ),
        ),
    ]
