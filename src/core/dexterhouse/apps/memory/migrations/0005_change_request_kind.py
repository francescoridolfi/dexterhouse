# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("memory", "0004_context_kind"),
        ("projects", "0006_change_requests"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="memorychunk",
            name="dh_memory_kind_valid",
        ),
        migrations.AlterField(
            model_name="memorychunk",
            name="kind",
            field=models.CharField(
                choices=[
                    ("adr", "adr"),
                    ("architecture", "architecture"),
                    ("assumptions", "assumptions"),
                    ("brief", "brief"),
                    ("code_graph", "code_graph"),
                    ("dev_notes", "dev_notes"),
                    ("file", "file"),
                    ("questions", "questions"),
                    ("release_notes", "release_notes"),
                    ("requirements", "requirements"),
                    ("retrospective", "retrospective"),
                    ("review", "review"),
                    ("stack", "stack"),
                    ("task_board", "task_board"),
                    ("team_proposal", "team_proposal"),
                    ("test_report", "test_report"),
                    ("user_stories", "user_stories"),
                    ("change_request", "change_request"),
                    ("context", "context"),
                    ("gate_comment", "gate_comment"),
                    ("note", "note"),
                    ("retro_lesson", "retro_lesson"),
                ],
                max_length=32,
            ),
        ),
        migrations.AddConstraint(
            model_name="memorychunk",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "kind__in",
                        (
                            "adr",
                            "architecture",
                            "assumptions",
                            "brief",
                            "code_graph",
                            "dev_notes",
                            "file",
                            "questions",
                            "release_notes",
                            "requirements",
                            "retrospective",
                            "review",
                            "stack",
                            "task_board",
                            "team_proposal",
                            "test_report",
                            "user_stories",
                            "change_request",
                            "context",
                            "gate_comment",
                            "note",
                            "retro_lesson",
                        ),
                    )
                ),
                name="dh_memory_kind_valid",
            ),
        ),
    ]
