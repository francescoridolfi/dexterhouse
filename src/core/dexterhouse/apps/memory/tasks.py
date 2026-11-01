# SPDX-License-Identifier: AGPL-3.0-or-later
"""Celery entry points: the projects app calls these when an artifact or comment is saved."""

import uuid
from typing import Any

from celery import shared_task

from dexterhouse.apps.memory.services.indexing import index_artifact, index_comment


@shared_task(
    name="dexterhouse.apps.memory.tasks.index_artifact",
    autoretry_for=(ConnectionError,),
    retry_backoff=True,
    max_retries=5,
)
def index_artifact_task(
    organization_id: str,
    project_id: str,
    artifact_id: str,
    version: int,
    kind: str,
    name: str = "",
    content: str | None = None,
    data: Any = None,
    untrusted: bool = False,
) -> int:
    """Index one artifact version; returns the number of chunks created (0 if up to date)."""
    return index_artifact(
        organization_id=uuid.UUID(organization_id),
        project_id=uuid.UUID(project_id),
        artifact_id=uuid.UUID(artifact_id),
        version=version,
        kind=kind,
        name=name,
        content=content,
        data=data,
        untrusted=untrusted,
    ).created


@shared_task(name="dexterhouse.apps.memory.tasks.index_comment")
def index_comment_task(
    organization_id: str, project_id: str, source_id: str, text: str, kind: str = "gate_comment"
) -> int:
    """Index a gate comment (weight 1.5) or a user note."""
    return index_comment(
        organization_id=uuid.UUID(organization_id),
        project_id=uuid.UUID(project_id),
        source_id=uuid.UUID(source_id),
        text=text,
        kind=kind,
    ).created
