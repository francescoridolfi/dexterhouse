# SPDX-License-Identifier: AGPL-3.0-or-later
"""Celery entry points of the projects app: they load ids and call services."""

import uuid

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

from dexterhouse.apps.projects.models import Artifact
from dexterhouse.apps.projects.services import context


@shared_task(
    name="dexterhouse.apps.projects.tasks.process_context", soft_time_limit=60, time_limit=90
)
def process_context(artifact_id: str) -> str:
    """Extract the text of a context document (60 s, then `failed: timeout`)."""
    try:
        return context.process_document(uuid.UUID(artifact_id))
    except SoftTimeLimitExceeded:
        return context.fail_document(Artifact.objects.get(pk=artifact_id), "timeout")
