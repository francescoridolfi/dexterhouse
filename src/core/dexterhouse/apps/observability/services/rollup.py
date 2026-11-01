# SPDX-License-Identifier: AGPL-3.0-or-later
"""Roll `LLMCall` rows older than `ROLLUP_AFTER_MONTHS` into `LLMUsageDaily` (CD-027)."""

from datetime import datetime, timedelta

import structlog
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from dexterhouse.apps.gateway.models import CallStatus, LLMCall
from dexterhouse.apps.observability.models import LLMUsageDaily

logger = structlog.get_logger(__name__)

ROLLUP_AFTER_MONTHS = 6


def cutoff(now: datetime | None = None, months: int = ROLLUP_AFTER_MONTHS) -> datetime:
    """Midnight `months` x 30 days ago: whole days only, so a day is never split."""
    now = now or timezone.now()
    day = (now - timedelta(days=30 * months)).date()
    return timezone.make_aware(datetime(day.year, day.month, day.day))


def rollup(before: datetime | None = None) -> int:
    """Aggregate and delete the calls created before `before`; returns the deleted rows."""
    before = before or cutoff()
    with transaction.atomic():
        ids = list(
            LLMCall.objects.select_for_update()
            .filter(created_at__lt=before)
            .values_list("id", flat=True)
        )
        old = LLMCall.objects.filter(pk__in=ids)
        groups = (
            old.annotate(day=TruncDate("created_at"))
            .values("organization_id", "project_id", "day", "provider", "model", "profile")
            .annotate(
                calls=Count("id"),
                errors=Count("id", filter=~Q(status=CallStatus.OK)),
                tokens_in=Coalesce(Sum("input_tokens"), 0),
                tokens_out=Coalesce(Sum("output_tokens"), 0),
                tokens_cached=Coalesce(Sum("cached_tokens"), 0),
                unpriced=Coalesce(
                    Sum(
                        F("input_tokens") + F("output_tokens"),
                        filter=Q(status=CallStatus.OK, cost__isnull=True),
                    ),
                    0,
                ),
                cost=Sum("cost", filter=Q(status=CallStatus.OK)),
            )
        )
        for g in groups:
            row, _ = LLMUsageDaily.objects.get_or_create(
                project_id=g["project_id"],
                day=g["day"],
                provider=g["provider"],
                model=g["model"],
                profile=g["profile"],
                defaults={"organization_id": g["organization_id"]},
            )
            row.calls += g["calls"]
            row.errors += g["errors"]
            row.input_tokens += g["tokens_in"]
            row.output_tokens += g["tokens_out"]
            row.cached_tokens += g["tokens_cached"]
            row.unpriced_tokens += g["unpriced"]
            row.cost += g["cost"] or 0
            row.save()
        deleted, _ = old.delete()
    if deleted:
        logger.info("costs.rolled_up", calls=deleted, before=before.isoformat())
    return deleted
