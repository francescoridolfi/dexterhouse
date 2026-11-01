# SPDX-License-Identifier: AGPL-3.0-or-later

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import dexterhouse.common.models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("accounts", "0002_default_organization"),
        ("projects", "0003_artifact_produced_by_turn"),
        ("workflows", "0002_integration_foreign_keys"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Notification",
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
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("gate_opened", "Gate Opened"),
                            ("gate_reminder", "Gate Reminder"),
                        ],
                        max_length=32,
                    ),
                ),
                ("title", models.CharField(max_length=200)),
                ("body", models.TextField(blank=True, default="")),
                ("data", models.JSONField(blank=True, default=dict)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("emailed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "gate",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notifications",
                        to="workflows.gate",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notifications",
                        to="accounts.organization",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notifications",
                        to="projects.project",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notifications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "dh_notifications_notification",
                "indexes": [
                    models.Index(fields=["user", "read_at"], name="dh_notification_unread")
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("kind__in", ["gate_opened", "gate_reminder"])),
                        name="dh_notification_kind_valid",
                    )
                ],
            },
        ),
    ]
