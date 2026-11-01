# SPDX-License-Identifier: AGPL-3.0-or-later
"""Append-only event log, partitioned by month on `created_at` (contracts/data_model/infra.md).

The table, its partitions and the immutability trigger are created with raw SQL in the
migrations; Django only knows the columns. Never UPDATE except `published`, never DELETE
(retention drops whole partitions).
"""

from django.db import models

from dexterhouse.common.models import new_id


class ActorType(models.TextChoices):
    AGENT = "agent"
    USER = "user"
    SYSTEM = "system"


class Event(models.Model):
    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    organization_id = models.UUIDField()
    project_id = models.UUIDField()
    type = models.CharField(max_length=80)
    schema_version = models.SmallIntegerField()
    actor_type = models.CharField(max_length=16, choices=ActorType.choices)
    actor_id = models.UUIDField(null=True, blank=True)
    actor_name = models.CharField(max_length=80, blank=True, default="")
    payload = models.JSONField()
    correlation_id = models.UUIDField()
    published = models.BooleanField(default=False)
    created_at = models.DateTimeField()

    class Meta:
        db_table = "dh_events_event"
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"{self.type} {self.id}"
