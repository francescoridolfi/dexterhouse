# SPDX-License-Identifier: AGPL-3.0-or-later
"""Workspace and SecretGrant (contracts/data_model/infra.md, state_machines/workspace.md).

The runner changes the container; the core mirrors its state from the runner's callbacks
(`core.runner.workspace_changed`) and only marks a quiet workspace `idle` itself. A
`SecretGrant` is a one-time reference to `Project.remote_token` that the runner redeems
within 60 s (CD-020): the token itself is never copied here.
"""

from django.db import models

from dexterhouse.apps.projects.models import Project
from dexterhouse.common.models import BaseModel


class WorkspaceStatus(models.TextChoices):
    REQUESTED = "requested"
    CREATING = "creating"
    READY = "ready"
    BUSY = "busy"
    IDLE = "idle"
    ERROR = "error"
    DESTROYING = "destroying"
    DESTROYED = "destroyed"


LIVE_STATUSES = (WorkspaceStatus.READY, WorkspaceStatus.BUSY, WorkspaceStatus.IDLE)
PENDING_STATUSES = (WorkspaceStatus.REQUESTED, WorkspaceStatus.CREATING)
TERMINAL_STATUSES = (WorkspaceStatus.DESTROYED,)


class Workspace(BaseModel):
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name="workspace")
    status = models.CharField(
        max_length=16, choices=WorkspaceStatus.choices, default=WorkspaceStatus.REQUESTED
    )
    image = models.CharField(max_length=200, blank=True, default="")
    digest = models.CharField(max_length=80, blank=True, default="")
    container_id = models.CharField(max_length=80, null=True, blank=True)
    volume = models.CharField(max_length=120, blank=True, default="")
    stack = models.JSONField(default=dict)
    services = models.JSONField(default=list)
    attempts = models.SmallIntegerField(default=0)
    last_activity_at = models.DateTimeField(null=True, blank=True)
    destroy_after = models.DateTimeField(null=True, blank=True)
    destroy_reason = models.CharField(max_length=16, blank=True, default="")
    error_detail = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "dh_workspaces_workspace"
        indexes = [
            models.Index(fields=["status", "last_activity_at"], name="dh_ws_status_activity")
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=WorkspaceStatus.values), name="dh_ws_status_valid"
            )
        ]

    def __str__(self) -> str:
        return f"workspace {self.id} ({self.status})"


class SecretGrant(BaseModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="secret_grants")
    purpose = models.CharField(max_length=16, default="deliver")
    secret_ref = models.CharField(max_length=64, default="project.remote_token")
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    requested_by_task = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "dh_workspaces_secret_grant"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(purpose__in=["deliver"]), name="dh_grant_purpose_valid"
            )
        ]

    def __str__(self) -> str:
        return f"grant {self.id} ({self.purpose})"
