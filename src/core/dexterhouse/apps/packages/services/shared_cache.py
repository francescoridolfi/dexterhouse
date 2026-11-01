# SPDX-License-Identifier: AGPL-3.0-or-later
"""A JSON cache in Redis, shared by the worker, the web process and the per-turn tool servers.

The marketplace tools run in a process that lives for one turn, so an in-process cache
would never be hit; Redis is. Redis being down only costs a fetch: errors are logged.
"""

import hashlib
import json
from typing import Any

import redis
import structlog

from dexterhouse.apps.events.services.streams import get_client

logger = structlog.get_logger(__name__)
PREFIX = "dh:marketplace:"


def key(*parts: Any) -> str:
    digest = hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()
    return f"{PREFIX}{parts[0]}:{digest[:32]}"


def get(name: str) -> Any:
    try:
        raw = get_client().get(name)
    except redis.RedisError as exc:
        logger.warning("marketplace.cache_unavailable", error=str(exc))
        return None
    return json.loads(raw) if raw else None


def put(name: str, value: Any, ttl_s: int) -> None:
    try:
        get_client().set(name, json.dumps(value, default=str), ex=ttl_s)
    except redis.RedisError as exc:
        logger.warning("marketplace.cache_unavailable", error=str(exc))


def clear() -> None:
    """Drop every marketplace entry (tests, `index.clear_cache`)."""
    try:
        client = get_client()
        names = list(client.scan_iter(f"{PREFIX}*"))
        if names:
            client.delete(*names)
    except redis.RedisError as exc:
        logger.warning("marketplace.cache_unavailable", error=str(exc))
