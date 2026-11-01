# SPDX-License-Identifier: AGPL-3.0-or-later
"""`GET /internal/secrets/{grant_id}`: the runner redeems a grant (infra/runner_protocol.md).

Authenticated by `X-Runner-Key` (the shared `runner_key` secret), not by a user session;
served on the `internal` network only (nginx does not proxy `/internal/`). 401 without the
key, 404 for an unknown, used or expired grant. The response is never cached.
"""

import hmac
import uuid

import structlog
from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from dexterhouse.apps.workspaces.grants import redeem

logger = structlog.get_logger(__name__)


@never_cache
@require_GET
def secret(request: HttpRequest, grant_id: uuid.UUID) -> HttpResponse:
    expected = settings.RUNNER_KEY
    given = request.headers.get("X-Runner-Key", "")
    if not expected or not hmac.compare_digest(given.encode(), expected.encode()):
        logger.warning("workspaces.grant_unauthorized", grant_id=str(grant_id))
        return JsonResponse({"detail": "unauthorized"}, status=401)
    value = redeem(grant_id)
    if value is None:
        logger.warning("workspaces.grant_refused", grant_id=str(grant_id))
        return JsonResponse({"detail": "not found"}, status=404)
    logger.info("workspaces.grant_redeemed", grant_id=str(grant_id))
    return JsonResponse({"value": value})
