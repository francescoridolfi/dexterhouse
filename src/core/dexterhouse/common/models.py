# SPDX-License-Identifier: AGPL-3.0-or-later
"""Abstract base model: UUIDv7 primary key and timestamps on every table."""

import uuid

from django.db import models
from uuid6 import uuid7


def new_id() -> uuid.UUID:
    """Return a time-ordered UUIDv7 as a standard `uuid.UUID`."""
    return uuid.UUID(bytes=uuid7().bytes)


class BaseModel(models.Model):
    """UUIDv7 `id`, `created_at`, `updated_at` (data model conventions)."""

    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
