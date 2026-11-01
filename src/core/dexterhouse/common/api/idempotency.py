# SPDX-License-Identifier: AGPL-3.0-or-later
"""`Idempotency-Key` on the POSTs that create resources (contracts/api/README.md).

The first response (status < 500) is kept for 24 h per organization, client and key; a retry
with the same body gets it back with `Idempotent-Replayed: true`. The same key with another
body is a 422, a key still being processed a 409. Raised errors are not kept: the client can
retry them with the same key.
"""

import hashlib
import json
from collections.abc import Callable
from functools import wraps
from typing import Any

from django.core.cache import cache
from rest_framework.request import Request
from rest_framework.response import Response

from dexterhouse.common.errors import ConflictError, DomainError, ValidationFailedError

HEADER = "Idempotency-Key"
TTL_S = 24 * 3600
PENDING_TTL_S = 120
MAX_KEY = 255


class IdempotencyKeyReusedError(DomainError):
    status = 422
    slug = "idempotency-key-reused"
    title = "Idempotency key reused"


def _fingerprint(request: Request) -> str:
    body = json.dumps(request.data, sort_keys=True, default=str)
    return hashlib.sha256(f"{request.method} {request.path}\n{body}".encode()).hexdigest()


def _cache_key(view: Any, key: str) -> str:
    ctx = view.ctx
    client = f"token:{ctx.token.pk}" if ctx.token is not None else f"user:{ctx.user.pk}"
    digest = hashlib.sha256(key.encode()).hexdigest()
    return f"dh:idem:{ctx.organization.pk}:{client}:{digest}"


def idempotent(handler: Callable[..., Response]) -> Callable[..., Response]:
    """Decorate an `ApiView.post` that creates a resource."""

    @wraps(handler)
    def wrapper(view: Any, request: Request, *args: Any, **kwargs: Any) -> Response:
        key = request.headers.get(HEADER)
        if key is None:
            return handler(view, request, *args, **kwargs)
        if not key or len(key) > MAX_KEY:
            raise ValidationFailedError(
                "invalid Idempotency-Key",
                [{"field": HEADER, "message": f"1 to {MAX_KEY} characters"}],
            )
        cache_key, fingerprint = _cache_key(view, key), _fingerprint(request)
        if not cache.add(cache_key, {"fingerprint": fingerprint, "done": False}, PENDING_TTL_S):
            stored = cache.get(cache_key) or {}
            if stored.get("fingerprint") != fingerprint:
                raise IdempotencyKeyReusedError("this key was used with a different request")
            if not stored.get("done"):
                raise ConflictError("a request with this key is still being processed")
            replay = Response(stored["data"], status=stored["status"])
            replay["Idempotent-Replayed"] = "true"
            return replay
        try:
            response = handler(view, request, *args, **kwargs)
        except BaseException:
            cache.delete(cache_key)
            raise
        if response.status_code >= 500:
            cache.delete(cache_key)
            return response
        record = {
            "fingerprint": fingerprint,
            "done": True,
            "status": response.status_code,
            "data": response.data,
        }
        cache.set(cache_key, record, TTL_S)
        return response

    return wrapper
