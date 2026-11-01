# SPDX-License-Identifier: AGPL-3.0-or-later
"""AgentInstance, AgentTurn, ToolCall (data_model/runtime.md, state_machines/agent_turn.md)."""

from django.contrib.postgres.fields import ArrayField
from django.db import models

from dexterhouse.apps.accounts.models import Organization
from dexterhouse.apps.projects.models import Project
from dexterhouse.common.models import BaseModel


class AgentStatus(models.TextChoices):
    IDLE = "idle"
    WORKING = "working"
    BLOCKED = "blocked"
    RELEASED = "released"


class AgentSource(models.TextChoices):
    BUILTIN = "builtin"
    MARKETPLACE = "marketplace"
    LOCAL = "local"


class AgentProfile(models.TextChoices):
    STRONG = "strong"
    BALANCED = "balanced"
    FAST = "fast"


class TurnStatus(models.TextChoices):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_TOOL = "waiting_tool"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TurnError(models.TextChoices):
    OUTPUT_CONTRACT = "output_contract"
    TOOL_LIMIT = "tool_limit"
    TIMEOUT = "timeout"
    PROVIDER = "provider"
    BUDGET = "budget"
    PERMISSION = "permission"
    CONTEXT_OVERFLOW = "context_overflow"
    CONFIGURATION = "configuration"


class ToolCallStatus(models.TextChoices):
    PENDING = "pending"
    DONE = "done"
    ERROR = "error"
    DENIED = "denied"


class AgentInstance(BaseModel):
    """An agent hired in a project; `allowed_tools` is what the tool gateway enforces."""

    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="+")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="agents")
    # The installed version this agent is pinned to (null: placeholder or test fixture).
    installed_version = models.ForeignKey(
        "packages.PackageVersion",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="agents",
        db_column="package_version_id",
    )
    package_name = models.CharField(max_length=120)
    package_version = models.CharField(max_length=32)
    package_path = models.CharField(max_length=300)  # directory holding agent.yaml
    role = models.CharField(max_length=64)
    display_name = models.CharField(max_length=80)
    model_profile = models.CharField(max_length=16, choices=AgentProfile.choices)
    allowed_tools = ArrayField(models.CharField(max_length=120), default=list, blank=True)
    room = models.CharField(max_length=64, blank=True, default="")
    avatar = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=AgentStatus.choices, default=AgentStatus.IDLE)
    source = models.CharField(
        max_length=16, choices=AgentSource.choices, default=AgentSource.BUILTIN
    )
    hired_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "dh_agents_agentinstance"
        indexes = [models.Index(fields=["project", "role"], name="dh_agent_project_role")]

    def __str__(self) -> str:
        return f"{self.display_name} ({self.role})"


class AgentTurn(BaseModel):
    """One turn, persisted at every step so a killed worker resumes it (ADR-0013).

    `inputs` is the work order given by the workflow engine (`TurnInputs`); `messages` the
    conversation so far; `tool_specs` the tools offered at the first call (stable on resume).
    """

    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="+")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="agent_turns")
    agent_instance = models.ForeignKey(
        AgentInstance, on_delete=models.PROTECT, related_name="turns"
    )
    phase_run = models.ForeignKey(
        "workflows.PhaseRun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agent_turns",
    )
    task = models.ForeignKey(
        "workflows.Task",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agent_turns",
    )
    # The workflow engine's idempotency key: one turn per (step run, attempt).
    step_run = models.ForeignKey(
        "workflows.StepRun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agent_turns",
    )
    step_attempt = models.IntegerField(default=1)
    step = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=16, choices=TurnStatus.choices, default=TurnStatus.QUEUED)
    purpose = models.CharField(max_length=120)
    inputs = models.JSONField(default=dict, blank=True)
    context_manifest = models.JSONField(default=dict, blank=True)
    tool_specs = models.JSONField(default=list, blank=True)
    messages = models.JSONField(default=list, blank=True)
    output = models.JSONField(null=True, blank=True)
    tool_calls_count = models.IntegerField(default=0)
    denied_count = models.IntegerField(default=0)
    reprompts = models.IntegerField(default=0)
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    cached_tokens = models.IntegerField(default=0)
    cost = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    profile_used = models.CharField(max_length=16, blank=True, default="")
    celery_task_id = models.CharField(max_length=64, blank=True, default="")
    attempt = models.IntegerField(default=0)
    error_code = models.CharField(max_length=32, choices=TurnError.choices, blank=True, default="")
    error_detail = models.TextField(blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "dh_agents_agentturn"
        indexes = [
            models.Index(fields=["project", "created_at"], name="dh_turn_project_created"),
            models.Index(fields=["agent_instance", "status"], name="dh_turn_agent_status"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=TurnStatus.values), name="dh_turn_status_valid"
            ),
            models.UniqueConstraint(
                fields=["step_run", "step_attempt"],
                condition=models.Q(step_run__isnull=False),
                name="dh_turn_step_run_attempt_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.purpose} [{self.status}]"


class ToolCall(BaseModel):
    """One tool invocation; `idempotency_key = <turn_id>:<seq>` makes retries safe."""

    agent_turn = models.ForeignKey(AgentTurn, on_delete=models.CASCADE, related_name="tool_calls")
    seq = models.IntegerField()
    idempotency_key = models.CharField(max_length=80, unique=True)
    call_id = models.CharField(max_length=120, blank=True, default="")
    tool = models.CharField(max_length=120)
    arguments = models.JSONField(default=dict, blank=True)  # secrets redacted
    allowed = models.BooleanField(default=True)
    result = models.JSONField(null=True, blank=True)  # truncated to 64 KB
    status = models.CharField(
        max_length=16, choices=ToolCallStatus.choices, default=ToolCallStatus.PENDING
    )
    denied_reason = models.CharField(max_length=64, blank=True, default="")
    duration_ms = models.IntegerField(default=0)

    class Meta:
        db_table = "dh_agents_toolcall"
        indexes = [models.Index(fields=["agent_turn", "seq"], name="dh_toolcall_turn_seq")]
        constraints = [
            models.UniqueConstraint(
                fields=["agent_turn", "seq"], name="dh_toolcall_turn_seq_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=ToolCallStatus.values),
                name="dh_toolcall_status_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.idempotency_key} {self.tool} {self.status}"
