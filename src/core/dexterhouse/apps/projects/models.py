# SPDX-License-Identifier: AGPL-3.0-or-later
"""Project, Artifact, Note (contracts/data_model/core.md, state_machines/project.md)."""

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.db import models

from dexterhouse.apps.accounts.models import Organization
from dexterhouse.common.models import BaseModel


class ProjectStatus(models.TextChoices):
    DRAFT = "draft"
    RUNNING = "running"
    WAITING = "waiting"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


class WaitingReason(models.TextChoices):
    GATE = "gate"
    BUDGET = "budget"
    PROVIDER = "provider"
    WORKSPACE = "workspace"


class ExecutionMode(models.TextChoices):
    SUPERVISED = "supervised"
    AUTONOMOUS = "autonomous"


class DataResidency(models.TextChoices):
    ANY = "any"
    LOCAL = "local"


class DeliveryMode(models.TextChoices):
    PUSH_MAIN = "push_main"
    PULL_REQUEST = "pull_request"


class ArtifactKind(models.TextChoices):
    BRIEF = "brief"
    REQUIREMENTS = "requirements"
    USER_STORIES = "user_stories"
    QUESTIONS = "questions"
    ASSUMPTIONS = "assumptions"
    ARCHITECTURE = "architecture"
    ADR = "adr"
    STACK = "stack"
    TASK_BOARD = "task_board"
    TEAM_PROPOSAL = "team_proposal"
    DEV_NOTES = "dev_notes"
    REVIEW = "review"
    TEST_REPORT = "test_report"
    RELEASE_NOTES = "release_notes"
    RETROSPECTIVE = "retrospective"
    FILE = "file"


class Project(BaseModel):
    """A brief taken from `draft` to `completed` by one process run."""

    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="projects"
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=64)
    brief = models.TextField(max_length=20_000)
    status = models.CharField(
        max_length=32, choices=ProjectStatus.choices, default=ProjectStatus.DRAFT
    )
    waiting_reason = models.CharField(
        max_length=32, choices=WaitingReason.choices, null=True, blank=True
    )
    execution_mode = models.CharField(
        max_length=32, choices=ExecutionMode.choices, default=ExecutionMode.SUPERVISED
    )
    gate_overrides = models.JSONField(default=dict, blank=True)
    # The packages app (E-07) replaces these two with `process_version` FK PackageVersion.
    process_name = models.CharField(max_length=64)
    process_version = models.CharField(max_length=32)
    model_profile_overrides = models.JSONField(null=True, blank=True)
    data_residency = models.CharField(
        max_length=16, choices=DataResidency.choices, default=DataResidency.ANY
    )
    budget = models.DecimalField(max_digits=12, decimal_places=6)
    spent = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    spent_unpriced_tokens = models.IntegerField(default=0)
    remote_repo_url = models.CharField(max_length=500, null=True, blank=True)
    remote_token = models.BinaryField(null=True, blank=True, editable=False)
    delivery_mode = models.CharField(
        max_length=32, choices=DeliveryMode.choices, default=DeliveryMode.PULL_REQUEST
    )
    stack = models.JSONField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="projects"
    )
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "dh_projects_project"
        indexes = [models.Index(fields=["organization", "status"], name="dh_project_org_status")]
        constraints = [
            models.UniqueConstraint(fields=["organization", "slug"], name="dh_project_slug_unique"),
            models.CheckConstraint(
                condition=models.Q(status__in=ProjectStatus.values), name="dh_project_status_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(execution_mode__in=ExecutionMode.values),
                name="dh_project_mode_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(budget__gte=0), name="dh_project_budget_non_negative"
            ),
        ]

    def __str__(self) -> str:
        return self.slug


class Artifact(BaseModel):
    """A versioned document; structured kinds carry validated `data`."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="artifacts")
    kind = models.CharField(max_length=32, choices=ArtifactKind.choices)
    name = models.CharField(max_length=200)
    version = models.PositiveIntegerField()
    content = models.TextField(blank=True, default="")
    data = models.JSONField(null=True, blank=True)
    content_hash = models.CharField(max_length=64)
    produced_by_turn_id = models.UUIDField(null=True, blank=True)  # FK added in E-03
    produced_by_role = models.CharField(max_length=64, blank=True, default="")
    phase_run = models.ForeignKey(
        "workflows.PhaseRun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="artifacts",
    )
    search = models.GeneratedField(
        expression=SearchVector("name", "content", config="english"),
        output_field=SearchVectorField(),
        db_persist=True,
    )

    class Meta:
        db_table = "dh_projects_artifact"
        indexes = [
            models.Index(fields=["project", "kind", "version"], name="dh_artifact_kind_version"),
            GinIndex(fields=["search"], name="dh_artifact_search"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "kind", "name", "version"], name="dh_artifact_version_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(kind__in=ArtifactKind.values), name="dh_artifact_kind_valid"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} v{self.version}"


class Note(BaseModel):
    """A user's note to the team; enters the context of the following turns."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="notes"
    )
    phase_run = models.ForeignKey(
        "workflows.PhaseRun", on_delete=models.SET_NULL, null=True, blank=True, related_name="notes"
    )
    content = models.TextField(max_length=10_000)
    consumed_by_turn_ids = ArrayField(models.UUIDField(), default=list, blank=True)

    class Meta:
        db_table = "dh_projects_note"

    def __str__(self) -> str:
        return f"note {self.id}"
