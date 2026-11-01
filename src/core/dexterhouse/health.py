# SPDX-License-Identifier: AGPL-3.0-or-later
"""Liveness and readiness probes (no auth, used by compose healthchecks)."""

import redis
import structlog
from django.conf import settings
from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

from dexterhouse import __version__

logger = structlog.get_logger(__name__)


def _check_database() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception as exc:  # any driver error means "not ready"
        logger.warning("health.database_failed", error=str(exc))
        return False
    return True


def _check_redis() -> bool:
    try:
        client = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=2)
        client.ping()
    except redis.RedisError as exc:
        logger.warning("health.redis_failed", error=str(exc))
        return False
    return True


@require_GET
def live(request: HttpRequest) -> JsonResponse:
    """The process answers."""
    return JsonResponse({"status": "ok", "version": __version__})


@require_GET
def ready(request: HttpRequest) -> JsonResponse:
    """Database and Redis are reachable (runner check arrives with the runner epic)."""
    checks = {"database": _check_database(), "redis": _check_redis()}
    ok = all(checks.values())
    return JsonResponse(
        {"status": "ok" if ok else "unavailable", "checks": checks}, status=200 if ok else 503
    )
