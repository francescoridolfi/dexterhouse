# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST v1 marketplace proxy (contracts/api/agents_packages.md, "Marketplace").

The same client as the Recruiter's `marketplace.*` tools (`packages.services.marketplace`),
with package texts unwrapped: people read them in the UI. Every response carries
`X-Marketplace-Source: api|index|cache|unreachable` (1.0: never `api`). Members read.
"""

from typing import Any

from rest_framework import exceptions
from rest_framework.request import Request
from rest_framework.response import Response

from dexterhouse.apps.packages.api.views import READ
from dexterhouse.apps.packages.services import marketplace
from dexterhouse.common.api import ApiView
from dexterhouse.common.errors import DomainError, ValidationFailedError

SOURCE_HEADER = "X-Marketplace-Source"
TRUE = {"1", "true", "yes", "on"}


class MarketplaceUnavailableError(DomainError):
    status = 503
    slug = "marketplace-unavailable"
    title = "Marketplace unavailable"


def _response(data: dict[str, Any], source: str) -> Response:
    response = Response(data)
    response[SOURCE_HEADER] = source
    return response


def _float(value: str | None, name: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise ValidationFailedError(
            f"{name} must be a number", [{"field": name, "message": "not a number"}]
        ) from exc


class MarketplaceSearchView(ApiView):
    def get(self, request: Request) -> Response:
        self.require(*READ)
        params = request.query_params
        kind = params.get("kind") or None
        if kind not in (None, "agent", "tool", "process"):
            raise ValidationFailedError(
                "invalid kind", [{"field": "kind", "message": "agent, tool or process"}]
            )
        tags = [t for t in params.get("tags", "").split(",") if t.strip()]
        limit = _float(params.get("limit"), "limit")
        result = marketplace.search(
            params.get("q", ""),
            kind,
            tags,
            params.get("verified", "").lower() in TRUE,
            _float(params.get("min_rating"), "min_rating"),
            int(limit) if limit is not None else 10,
            mark_untrusted=False,
        )
        return _response(result, result["source"])


class MarketplacePackageView(ApiView):
    def get(self, request: Request, name: str) -> Response:
        ctx = self.require(*READ)
        try:
            data = marketplace.details(name, ctx.organization.id, mark_untrusted=False)
        except marketplace.PackageNotFoundError as exc:
            raise exceptions.NotFound(str(exc)) from exc
        except marketplace.MarketplaceUnavailableError as exc:
            raise MarketplaceUnavailableError(str(exc)) from exc
        return _response(data, data["source"])


class MarketplaceStatusView(ApiView):
    def get(self, request: Request) -> Response:
        self.require(*READ)
        data = marketplace.status()
        return _response(data, data["source"])
