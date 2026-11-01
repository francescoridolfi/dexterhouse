# SPDX-License-Identifier: AGPL-3.0-or-later
"""Celery tasks: load the id, call the service (coding standards)."""

import uuid

from celery import shared_task

from dexterhouse.apps.notifications import services


@shared_task(
    name="dexterhouse.apps.notifications.tasks.send_email",
    autoretry_for=(OSError,),
    retry_backoff=True,
    max_retries=5,
)
def send_email(notification_id: str) -> bool:
    return services.send_email(uuid.UUID(notification_id))
