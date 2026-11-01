# SPDX-License-Identifier: AGPL-3.0-or-later
"""RFC 9457 `application/problem+json` for every API error (contracts/api/README.md)."""

import math
from typing import Any

from django.http import Http404
from rest_framework import exceptions
from rest_framework.response import Response

from dexterhouse.common.errors import DomainError

PROBLEM_TYPE = "https://dexterhouse.dev/errors/"
CONTENT_TYPE = "application/problem+json"


def problem(
    *,
    status: int,
    slug: str,
    title: str,
    detail: str,
    instance: str,
    errors: list[dict[str, str]] | None = None,
) -> Response:
    body = {
        "type": PROBLEM_TYPE + slug,
        "title": title,
        "status": status,
        "detail": detail,
        "instance": instance,
        "errors": errors or [],
    }
    return Response(body, status=status, content_type=CONTENT_TYPE)


def flatten_errors(detail: Any, prefix: str = "") -> list[dict[str, str]]:
    """DRF `ValidationError.detail` as `[{field, message}]` (dotted fields, `[i]` indexes)."""
    if isinstance(detail, dict):
        out: list[dict[str, str]] = []
        for key, value in detail.items():
            field = f"{prefix}.{key}" if prefix else str(key)
            if key == "non_field_errors":
                field = prefix
            out.extend(flatten_errors(value, field))
        return out
    if isinstance(detail, list):
        if all(not isinstance(item, dict | list) for item in detail):
            return [{"field": prefix, "message": str(item)} for item in detail]
        out = []
        for index, item in enumerate(detail):
            out.extend(flatten_errors(item, f"{prefix}[{index}]"))
        return out
    return [{"field": prefix, "message": str(detail)}]


def problem_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """DRF exception handler; unknown exceptions return None (Django's 500)."""
    request = context.get("request")
    instance = request.path if request is not None else ""
    if isinstance(exc, DomainError):
        return problem(
            status=exc.status,
            slug=exc.slug,
            title=exc.title,
            detail=exc.detail,
            instance=instance,
            errors=exc.errors,
        )
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    if isinstance(exc, exceptions.ValidationError):
        return problem(
            status=400,
            slug="validation-error",
            title="Validation failed",
            detail="The request body or parameters are not valid.",
            instance=instance,
            errors=flatten_errors(exc.detail),
        )
    if isinstance(exc, exceptions.Throttled):
        response = problem(
            status=429,
            slug="rate-limited",
            title="Too many requests",
            detail=str(exc.detail),
            instance=instance,
        )
        if exc.wait is not None:
            response["Retry-After"] = str(max(1, math.ceil(exc.wait)))
        return response
    if isinstance(exc, exceptions.APIException):
        response = problem(
            status=exc.status_code,
            slug=str(exc.default_code).replace("_", "-"),
            title=str(exc.default_detail),
            detail=str(exc.detail),
            instance=instance,
        )
        if isinstance(exc, exceptions.NotAuthenticated | exceptions.AuthenticationFailed):
            authenticator = (
                request.authenticators[0] if request and request.authenticators else None
            )
            header = authenticator.authenticate_header(request) if authenticator else None
            if header:
                response["WWW-Authenticate"] = header
        return response
    return None
