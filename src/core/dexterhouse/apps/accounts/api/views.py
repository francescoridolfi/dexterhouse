# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST v1: session auth for the SPA, organization and members (admin.md, frontend security).

The SPA authenticates with Django's session cookie (HttpOnly, SameSite=Lax) and sends the
`csrftoken` cookie back as `X-CSRFToken`; no token is ever stored in browser storage.
"""

from typing import Any

from django.contrib.auth import authenticate, login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from dexterhouse.apps.accounts.models import Membership, Organization, Role, Scope, User
from dexterhouse.common.api import ApiView
from dexterhouse.common.errors import DomainError

READ = (Role.VIEWER, Scope.PROJECTS_READ)
OWNER = (Role.OWNER, Scope.PROJECTS_WRITE)
SETTINGS_KEYS = frozenset({"language", "gate_ttl_hours", "events_retention_months", "telemetry"})


def user_json(user: User) -> dict[str, Any]:
    memberships = Membership.objects.filter(user=user).select_related("organization")
    return {
        "id": str(user.id),
        "username": user.get_username(),
        "email": user.email,
        "display_name": user.get_full_name() or user.get_username(),
        "organizations": [
            {"slug": m.organization.slug, "name": m.organization.name, "role": m.role}
            for m in memberships.order_by("created_at")
        ],
    }


def organization_json(org: Organization) -> dict[str, Any]:
    return {
        "id": str(org.id),
        "slug": org.slug,
        "name": org.name,
        "settings": org.settings,
        "budget_monthly": str(org.budget_monthly) if org.budget_monthly is not None else None,
        "spent_month": str(org.spent_month),
    }


class InvalidCredentialsError(DomainError):
    status = 401
    slug = "invalid-credentials"
    title = "Invalid credentials"


class LoginInput(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=256, trim_whitespace=False)


@method_decorator(ensure_csrf_cookie, name="get")
class CsrfView(ApiView):
    """Sets the `csrftoken` cookie; the SPA calls it once before the first POST."""

    authentication_classes = ()
    permission_classes = (AllowAny,)

    def get(self, request: Request) -> Response:
        return Response({"detail": "ok"})


@method_decorator(csrf_protect, name="post")
class LoginView(ApiView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def post(self, request: Request) -> Response:
        body = LoginInput(data=request.data)
        body.is_valid(raise_exception=True)
        user = authenticate(request._request, **body.validated_data)
        if user is None or not user.is_active:
            raise InvalidCredentialsError("invalid username or password")
        login(request._request, user)
        return Response(user_json(user))


class LogoutView(ApiView):
    def post(self, request: Request) -> Response:
        logout(request._request)
        return Response(status=204)


class MeView(ApiView):
    def get(self, request: Request) -> Response:
        return Response(user_json(request.user))


class OrganizationInput(serializers.Serializer):
    name = serializers.CharField(max_length=120, required=False)
    settings = serializers.DictField(required=False)

    def validate_settings(self, value: dict[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(value) - SETTINGS_KEYS)
        if unknown:
            raise serializers.ValidationError(f"unknown settings: {', '.join(unknown)}")
        return value


class OrganizationView(ApiView):
    def get(self, request: Request) -> Response:
        return Response(organization_json(self.require(*READ).organization))

    def patch(self, request: Request) -> Response:
        ctx = self.require(*OWNER)
        body = OrganizationInput(data=request.data, partial=True)
        body.is_valid(raise_exception=True)
        org = ctx.organization
        if "name" in body.validated_data:
            org.name = body.validated_data["name"]
        if "settings" in body.validated_data:
            org.settings = {**org.settings, **body.validated_data["settings"]}
        org.save(update_fields=["name", "settings", "updated_at"])
        return Response(organization_json(org))


class MembersView(ApiView):
    def get(self, request: Request) -> Response:
        ctx = self.require(*READ)
        rows = Membership.objects.filter(organization=ctx.organization).select_related("user")
        return Response(
            {
                "results": [
                    {
                        "id": str(m.id),
                        "user": {"id": str(m.user_id), "username": m.user.get_username()},
                        "role": m.role,
                        "created_at": m.created_at.isoformat(),
                    }
                    for m in rows.order_by("created_at")
                ]
            }
        )
