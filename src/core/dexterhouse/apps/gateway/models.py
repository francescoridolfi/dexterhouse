# SPDX-License-Identifier: AGPL-3.0-or-later
"""LLMCall: one row per provider call with tokens and EUR cost (data_model/runtime.md)."""

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


class LLMCall(BaseModel):
    """`project_id` and `agent_turn_id` become foreign keys when those apps exist (Sprint 1+)."""

    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="+")
    project_id = models.UUIDField()
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

    class Meta:
        db_table = "dh_gateway_llmcall"
        indexes = [
            models.Index(fields=["organization", "created_at"], name="dh_llmcall_org_created"),
            models.Index(fields=["project_id", "created_at"], name="dh_llmcall_project_created"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=CallStatus.values), name="dh_llmcall_status_valid"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider}/{self.model} {self.status}"
