# SPDX-License-Identifier: AGPL-3.0-or-later
"""One-time grants for the git token (CD-020, ST-16).

`create_grant` stores only a reference; `redeem` decrypts `Project.remote_token` once,
within 60 s, and consumes the grant in the same transaction: a second read, an expired
grant or an unknown id are all `None` (the endpoint answers 404 alike).
"""

import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from dexterhouse.apps.projects.models import Project
from dexterhouse.apps.workspaces.models import SecretGrant
from dexterhouse.common import crypto

GRANT_TTL = timedelta(seconds=60)


def create_grant(project: Project, requested_by_task: str = "") -> SecretGrant:
    return SecretGrant.objects.create(
        project=project,
        purpose="deliver",
        expires_at=timezone.now() + GRANT_TTL,
        requested_by_task=requested_by_task[:64],
    )


def redeem(grant_id: uuid.UUID) -> str | None:
    with transaction.atomic():
        grant = (
            SecretGrant.objects.select_for_update()
            .select_related("project")
            .filter(pk=grant_id, consumed_at__isnull=True)
            .first()
        )
        if grant is None:
            return None
        grant.consumed_at = timezone.now()
        grant.save(update_fields=["consumed_at", "updated_at"])
        if grant.expires_at < grant.consumed_at or not grant.project.remote_token:
            return None
        return crypto.decrypt(grant.project.remote_token)


def purge(before=None) -> int:
    """Delete consumed or expired grants (the token was never stored in them)."""
    before = before or timezone.now()
    consumed = SecretGrant.objects.filter(consumed_at__isnull=False).delete()[0]
    expired = SecretGrant.objects.filter(expires_at__lt=before).delete()[0]
    return consumed + expired
