# SPDX-License-Identifier: AGPL-3.0-or-later
"""`llm_usage_daily`: LLM calls rolled up per day after the retention window (CD-027)."""

from django.db import models

from dexterhouse.apps.accounts.models import Organization
from dexterhouse.common.models import BaseModel


class LLMUsageDaily(BaseModel):
    """One row per (project, day, provider, model, profile) for calls older than 6 months.

    The raw `LLMCall` rows are deleted once rolled up: project spend and the per-day and
    per-provider aggregates keep counting them; per-phase and per-agent views lose them.
    """

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="llm_usage_daily"
    )
    day = models.DateField()
    provider = models.CharField(max_length=64)
    model = models.CharField(max_length=64)
    profile = models.CharField(max_length=16)
    calls = models.IntegerField(default=0)
    errors = models.IntegerField(default=0)
    input_tokens = models.BigIntegerField(default=0)
    output_tokens = models.BigIntegerField(default=0)
    cached_tokens = models.BigIntegerField(default=0)
    unpriced_tokens = models.BigIntegerField(default=0)
    cost = models.DecimalField(max_digits=14, decimal_places=6, default=0)

    class Meta:
        db_table = "dh_observability_llm_usage_daily"
        constraints = [
            models.UniqueConstraint(
                fields=["project", "day", "provider", "model", "profile"],
                name="dh_usage_daily_unique",
            )
        ]
        indexes = [models.Index(fields=["organization", "day"], name="dh_usage_daily_org_day")]

    def __str__(self) -> str:
        return f"{self.project_id} {self.day} {self.provider}/{self.model}"
