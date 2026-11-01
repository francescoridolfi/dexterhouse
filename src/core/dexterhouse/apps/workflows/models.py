# SPDX-License-Identifier: AGPL-3.0-or-later
"""ProcessRun, PhaseRun, Task, Gate (contracts/data_model/workflow.md) and StepRun.

`StepRun` is the engine's idempotency record: one row per agent turn the process asks for.
It is created under the ProcessRun lock, at most one is active per phase run, and its output
is applied exactly once (ADR-0013). `AgentTurn.step_run` links the agent turns to it.
"""

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone

from dexterhouse.apps.projects.models import Project
from dexterhouse.common.models import BaseModel


class ProcessRunStatus(models.TextChoices):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_GATE = "waiting_gate"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PhaseStatus(models.TextChoices):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    WAITING_GATE = "waiting_gate"
    REOPENED = "reopened"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PhaseStage(models.TextChoices):
    STEPS = "steps"
    AFTER_GATE = "after_gate"


class TaskKind(models.TextChoices):
    FEATURE = "feature"
    FIX = "fix"


class TaskStatus(models.TextChoices):
    PENDING = "pending"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    IN_TEST = "in_test"
    DONE = "done"
    ESCALATED = "escalated"
    CANCELLED = "cancelled"


class Estimate(models.TextChoices):
    S = "S"
    M = "M"
    L = "L"


class GateType(models.TextChoices):
    APPROVAL = "approval"
    QUESTION = "question"
    ESCALATION = "escalation"


class GateStatus(models.TextChoices):
    OPEN = "open"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPROVED_WITH_COMMENTS = "approved_with_comments"
    ANSWERED = "answered"
    AUTO_APPROVED = "auto_approved"
    EXPIRED = "expired"


class GateDecision(models.TextChoices):
    APPROVE = "approve"
    REJECT = "reject"
    APPROVE_WITH_COMMENTS = "approve_with_comments"
    RETRY = "retry"
    ACCEPT = "accept"
    DROP = "drop"


class StepRunStatus(models.TextChoices):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIVE_TASK_STATUSES = (TaskStatus.IN_PROGRESS, TaskStatus.IN_REVIEW, TaskStatus.IN_TEST)
ACTIVE_STEP_STATUSES = (StepRunStatus.QUEUED, StepRunStatus.RUNNING)


def _status_check(name: str, values: list[str]) -> models.CheckConstraint:
    return models.CheckConstraint(condition=models.Q(status__in=values), name=name)


class ProcessRun(BaseModel):
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name="process_run")
    # The packages app (E-07) adds `process_version` FK PackageVersion.
    process_name = models.CharField(max_length=64)
    process_version = models.CharField(max_length=32)
    definition = models.JSONField()
    status = models.CharField(
        max_length=32, choices=ProcessRunStatus.choices, default=ProcessRunStatus.PENDING
    )
    error_code = models.CharField(max_length=64, null=True, blank=True)
    error_detail = models.TextField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "dh_workflows_processrun"
        constraints = [_status_check("dh_processrun_status_valid", ProcessRunStatus.values)]

    def __str__(self) -> str:
        return f"{self.process_name}@{self.process_version}"


class PhaseRun(BaseModel):
    process_run = models.ForeignKey(ProcessRun, on_delete=models.CASCADE, related_name="phases")
    phase_id = models.CharField(max_length=64)
    position = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=32, choices=PhaseStatus.choices, default="pending")
    stage = models.CharField(max_length=16, choices=PhaseStage.choices, default="steps")
    current_step = models.PositiveSmallIntegerField(default=0)
    round = models.PositiveSmallIntegerField(default=0)
    reopen_count = models.PositiveSmallIntegerField(default=0)
    exit_attempts = models.PositiveSmallIntegerField(default=0)
    context = models.JSONField(default=dict, blank=True)  # PhaseContext
    room = models.CharField(max_length=64)
    error_code = models.CharField(max_length=64, null=True, blank=True)
    needs_satisfied_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "dh_workflows_phaserun"
        ordering = ["position"]
        indexes = [models.Index(fields=["process_run", "status"], name="dh_phaserun_status")]
        constraints = [
            models.UniqueConstraint(fields=["process_run", "phase_id"], name="dh_phaserun_unique"),
            _status_check("dh_phaserun_status_valid", PhaseStatus.values),
        ]

    def __str__(self) -> str:
        return self.phase_id


class Task(BaseModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks")
    phase_run = models.ForeignKey(PhaseRun, on_delete=models.CASCADE, related_name="tasks")
    external_id = models.CharField(max_length=16)
    kind = models.CharField(max_length=16, choices=TaskKind.choices, default=TaskKind.FEATURE)
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )
    iteration = models.PositiveSmallIntegerField(default=1)
    max_iterations = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    acceptance = models.JSONField(default=list)
    depends_on = ArrayField(models.UUIDField(), default=list, blank=True)
    estimate = models.CharField(max_length=1, choices=Estimate.choices, default=Estimate.M)
    assigned_role = models.CharField(max_length=64)
    assigned_instance = models.ForeignKey(
        "agents.AgentInstance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
    )
    status = models.CharField(max_length=32, choices=TaskStatus.choices, default="pending")
    branch = models.CharField(max_length=120, null=True, blank=True)
    order = models.PositiveIntegerField(default=0)
    current_step = models.CharField(max_length=32, null=True, blank=True)
    result = models.JSONField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "dh_workflows_task"
        indexes = [
            models.Index(fields=["project", "status"], name="dh_task_project_status"),
            models.Index(fields=["phase_run", "order"], name="dh_task_phase_order"),
        ]
        constraints = [
            # One top-level task per external id; fix children are unique per iteration.
            models.UniqueConstraint(
                fields=["project", "external_id"],
                condition=models.Q(parent__isnull=True),
                name="dh_task_external_unique",
            ),
            models.UniqueConstraint(
                fields=["parent", "iteration"],
                condition=models.Q(parent__isnull=False),
                name="dh_task_fix_iteration_unique",
            ),
            _status_check("dh_task_status_valid", TaskStatus.values),
        ]

    def __str__(self) -> str:
        return f"{self.external_id}#{self.iteration}"


class Gate(BaseModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="gates")
    phase_run = models.ForeignKey(PhaseRun, on_delete=models.CASCADE, related_name="gates")
    task = models.ForeignKey(
        Task, on_delete=models.CASCADE, null=True, blank=True, related_name="gates"
    )
    gate_id = models.CharField(max_length=64)
    type = models.CharField(max_length=16, choices=GateType.choices)
    status = models.CharField(max_length=32, choices=GateStatus.choices, default="open")
    payload = models.JSONField(default=dict)  # GatePayload, immutable after opening
    decision = models.CharField(max_length=32, choices=GateDecision.choices, null=True, blank=True)
    comment = models.TextField(null=True, blank=True)
    answers = models.JSONField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="gate_decisions",
    )
    opened_at = models.DateTimeField(default=timezone.now)
    decided_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    notified_at = models.DateTimeField(null=True, blank=True)
    reminders = models.PositiveSmallIntegerField(default=0)  # `gate.renotified` sent so far

    class Meta:
        db_table = "dh_workflows_gate"
        indexes = [models.Index(fields=["project", "status"], name="dh_gate_project_status")]
        constraints = [_status_check("dh_gate_status_valid", GateStatus.values)]

    def __str__(self) -> str:
        return f"{self.gate_id} ({self.status})"


class StepRun(BaseModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="step_runs")
    phase_run = models.ForeignKey(PhaseRun, on_delete=models.CASCADE, related_name="step_runs")
    task = models.ForeignKey(
        Task, on_delete=models.CASCADE, null=True, blank=True, related_name="step_runs"
    )
    seq = models.PositiveIntegerField()
    stage = models.CharField(max_length=16, choices=PhaseStage.choices, default="steps")
    step_index = models.PositiveSmallIntegerField()
    step = models.CharField(max_length=64)
    role = models.CharField(max_length=64)
    agent = models.ForeignKey(
        "agents.AgentInstance", on_delete=models.PROTECT, related_name="step_runs"
    )
    agent_turn = models.ForeignKey(  # the turn of the latest attempt (AgentsTurnRunner)
        "agents.AgentTurn",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    round = models.PositiveSmallIntegerField(default=0)
    iteration = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=16, choices=StepRunStatus.choices, default="queued")
    attempts = models.PositiveSmallIntegerField(default=0)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    request = models.JSONField(default=dict)  # TurnRequest as sent to the runner
    output = models.JSONField(null=True, blank=True)  # validated TurnOutput
    error = models.TextField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "dh_workflows_steprun"
        ordering = ["created_at"]
        indexes = [models.Index(fields=["status", "updated_at"], name="dh_steprun_status")]
        constraints = [
            models.UniqueConstraint(fields=["phase_run", "seq"], name="dh_steprun_seq_unique"),
            models.UniqueConstraint(
                fields=["phase_run"],
                condition=models.Q(status__in=ACTIVE_STEP_STATUSES),
                name="dh_steprun_one_active_per_phase",
            ),
            _status_check("dh_steprun_status_valid", StepRunStatus.values),
        ]

    def __str__(self) -> str:
        return f"{self.phase_run_id}#{self.seq} {self.step}"
