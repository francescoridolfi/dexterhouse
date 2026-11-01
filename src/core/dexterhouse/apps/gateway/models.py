# SPDX-License-Identifier: AGPL-3.0-or-later
"""LLMCall and ModelProfile (data_model/runtime.md, data_model/infra.md)."""

from django.core.exceptions import ValidationError
from django.db import models

from dexterhouse.apps.accounts.models import Organization
from dexterhouse.common.models import BaseModel


class CallStatus(models.TextChoices):
    OK = "ok"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"


class ProfileChoice(models.TextChoices):
    STRONG = "strong"
    BALANCED = "balanced"
    FAST = "fast"
    EMBED = "embed"


class ProviderChoice(models.TextChoices):
    ANTHROPIC = "anthropic"
    ANTHROPIC_CLI = "anthropic-cli"
    OPENAI = "openai"
    OPENAI_COMPATIBLE = "openai-compatible"
    OLLAMA = "ollama"
    FAKE = "fake"


class LLMCall(BaseModel):
    """`project_id` and `agent_turn_id` become foreign keys at integration (E-02).

    A successful call made under an `idempotency_key` stores its aggregated `response`, so a
    resumed turn reuses it instead of calling the provider again (ADR-0013).
    """

    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="+")
    project_id = models.UUIDField()  # FK added at integration (E-02)
    agent_turn_id = models.UUIDField(null=True, blank=True)
    provider = models.CharField(max_length=64)
    model = models.CharField(max_length=64)
    profile = models.CharField(max_length=16, choices=ProfileChoice.choices)
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    cached_tokens = models.IntegerField(default=0)
    cache_write_tokens = models.IntegerField(default=0)
    cost = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    price_version = models.CharField(max_length=32, blank=True, default="")
    latency_ms = models.IntegerField(default=0)
    status = models.CharField(max_length=16, choices=CallStatus.choices)
    error_detail = models.TextField(blank=True, default="")
    trace_id = models.CharField(max_length=64, blank=True, default="")
    idempotency_key = models.CharField(max_length=120, blank=True, default="")
    response = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "dh_gateway_llmcall"
        indexes = [
            models.Index(fields=["organization", "created_at"], name="dh_llmcall_org_created"),
            models.Index(fields=["project_id", "created_at"], name="dh_llmcall_project_created"),
            models.Index(fields=["agent_turn_id"], name="dh_llmcall_turn"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=CallStatus.values), name="dh_llmcall_status_valid"
            ),
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=models.Q(status="ok") & ~models.Q(idempotency_key=""),
                name="dh_llmcall_idempotency_ok",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider}/{self.model} {self.status}"


class ModelProfile(BaseModel):
    """Profile → provider + model for an organization, overridable per project.

    Keys are never stored: `api_key_env` names the environment variable to read (default:
    the provider's own, e.g. `ANTHROPIC_API_KEY`). `options`: `temperature`, `max_tokens`,
    `allow_downgrade`, `acknowledge_cli_terms` (required for `anthropic-cli`), `matryoshka`.
    """

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="model_profiles"
    )
    project_id = models.UUIDField(null=True, blank=True)  # FK added at integration (E-02)
    profile = models.CharField(max_length=16, choices=ProfileChoice.choices)
    provider = models.CharField(max_length=32, choices=ProviderChoice.choices)
    model = models.CharField(max_length=120)
    base_url = models.CharField(max_length=300, blank=True, default="")
    api_key_env = models.CharField(max_length=64, blank=True, default="")
    options = models.JSONField(default=dict, blank=True)
    is_local = models.BooleanField(default=False)

    class Meta:
        db_table = "dh_gateway_modelprofile"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "profile"],
                condition=models.Q(project_id__isnull=True),
                name="dh_modelprofile_org_unique",
            ),
            models.UniqueConstraint(
                fields=["organization", "project_id", "profile"],
                condition=models.Q(project_id__isnull=False),
                name="dh_modelprofile_project_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(profile__in=ProfileChoice.values),
                name="dh_modelprofile_profile_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(provider__in=ProviderChoice.values),
                name="dh_modelprofile_provider_valid",
            ),
        ]

    def __str__(self) -> str:
        scope = self.project_id or self.organization_id
        return f"{scope}:{self.profile} → {self.provider}/{self.model}"

    def clean(self) -> None:
        if self.provider == ProviderChoice.ANTHROPIC_CLI and not self.options.get(
            "acknowledge_cli_terms"
        ):
            raise ValidationError(
                "anthropic-cli is opt-in: set options.acknowledge_cli_terms after reading "
                "docs/providers/anthropic-cli.md (your plan's terms are your responsibility)"
            )
        if self.provider == ProviderChoice.ANTHROPIC_CLI and self.profile == ProfileChoice.EMBED:
            raise ValidationError("anthropic-cli provides no embeddings")

    def save(self, *args: object, **kwargs: object) -> None:
        self.full_clean(exclude=["organization"])
        super().save(*args, **kwargs)  # type: ignore[arg-type]
