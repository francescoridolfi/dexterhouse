# SPDX-License-Identifier: AGPL-3.0-or-later
"""Celery beat jobs of the event bus (thin wrappers around services)."""

from celery import shared_task
from django.conf import settings

from dexterhouse.apps.events.services import partitions, publisher


@shared_task(name="dexterhouse.apps.events.tasks.republish_pending")
def republish_pending() -> int:
    return publisher.republish_pending()


@shared_task(name="dexterhouse.apps.events.tasks.maintain_partitions")
def maintain_partitions() -> dict[str, list[str]]:
    return {
        "created": partitions.ensure_partitions(),
        "dropped": partitions.drop_expired_partitions(settings.EVENTS_RETENTION_MONTHS),
    }
