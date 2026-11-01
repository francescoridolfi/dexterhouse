# SPDX-License-Identifier: AGPL-3.0-or-later
"""Redis Streams transport: one stream per project, entries carry the JSON envelope."""

import uuid
from functools import lru_cache

import redis
import redis.asyncio as aioredis
from django.conf import settings

from dexterhouse.apps.events.schemas import EventEnvelope

FIELD = "event"


def stream_key(project_id: uuid.UUID | str) -> str:
    return f"dh:events:project:{project_id}"


@lru_cache(maxsize=4)
def _client(url: str) -> redis.Redis:
    return redis.Redis.from_url(url, socket_timeout=5, socket_connect_timeout=5)


def get_client() -> redis.Redis:
    """Process-wide sync client for `settings.REDIS_URL`."""
    return _client(settings.REDIS_URL)


def get_async_client() -> aioredis.Redis:
    """New asyncio client (one per WebSocket connection, closed by the caller)."""
    return aioredis.Redis.from_url(settings.REDIS_URL)


def append(envelope: EventEnvelope, client: redis.Redis | None = None) -> str:
    """XADD the envelope to its project stream (approximate MAXLEN) and return the entry id."""
    client = client or get_client()
    entry_id = client.xadd(
        stream_key(envelope.project_id),
        {FIELD: envelope.model_dump_json()},
        maxlen=settings.EVENTS_STREAM_MAXLEN,
        approximate=True,
    )
    return _id(entry_id)


def decode(fields: dict[bytes, bytes]) -> EventEnvelope:
    """Parse a stream entry back into an envelope."""
    return EventEnvelope.model_validate_json(fields[FIELD.encode()])


def latest_id(project_id: uuid.UUID | str, client: redis.Redis | None = None) -> str:
    """Id of the newest entry of the project stream, `0-0` if the stream is empty."""
    client = client or get_client()
    entries = client.xrevrange(stream_key(project_id), count=1)
    return _id(entries[0][0]) if entries else "0-0"


def read_after(
    project_id: uuid.UUID | str,
    last_id: str,
    *,
    block_ms: int | None = None,
    count: int = 100,
    client: redis.Redis | None = None,
) -> list[tuple[str, EventEnvelope]]:
    """Entries after `last_id` (`$` = only new ones), waiting up to `block_ms` if none."""
    client = client or get_client()
    response = client.xread({stream_key(project_id): last_id}, block=block_ms, count=count)
    return [
        (_id(entry_id), decode(fields))
        for _key, entries in response or []
        for entry_id, fields in entries
    ]


def _id(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value
