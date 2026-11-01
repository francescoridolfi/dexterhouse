# SPDX-License-Identifier: AGPL-3.0-or-later
from celery import shared_task

from dexterhouse.apps.observability.services import rollup


@shared_task(name="dexterhouse.apps.observability.tasks.rollup_llm_calls")
def rollup_llm_calls() -> int:
    """Beat, monthly: `LLMCall` older than 6 months → `llm_usage_daily` (CD-027)."""
    return rollup.rollup()
