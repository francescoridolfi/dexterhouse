# SPDX-License-Identifier: AGPL-3.0-or-later
"""In-app notifications for one user (F-004): bell in the 3D office, badge in the 2D UI."""

from django.conf import settings
from django.db import models

from dexterhouse.apps.accounts.models import Organization
from dexterhouse.common.models import BaseModel


class NotificationKind(models.TextChoices):
    GATE_OPENED = "gate_opened"
    GATE_REMINDER = "gate_reminder"


class Notification(BaseModel):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="notifications"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )
    gate = models.ForeignKey(
        "workflows.Gate",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )
    kind = models.CharField(max_length=32, choices=NotificationKind.choices)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True, default="")
    data = models.JSONField(default=dict, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    emailed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "dh_notifications_notification"
        indexes = [models.Index(fields=["user", "read_at"], name="dh_notification_unread")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind__in=NotificationKind.values),
                name="dh_notification_kind_valid",
            )
        ]

    def __str__(self) -> str:
        return f"{self.kind} for {self.user_id}"
