# SPDX-License-Identifier: AGPL-3.0-or-later
"""Base view: organization context (`X-Organization` or default), role and scope checks."""

from collections.abc import Callable
from dataclasses import dataclass
from functools import cached_property
from typing import Any

from django.db.models import QuerySet
from rest_framework import exceptions
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from dexterhouse.apps.accounts.models import ApiToken, Membership, Organization, Role, User
from dexterhouse.common.api.pagination import CursorPage
from dexterhouse.common.api.problems import problem_exception_handler

ROLE_RANK = {Role.VIEWER: 0, Role.MEMBER: 1, Role.ADMIN: 2, Role.OWNER: 3}
ORG_HEADER = "X-Organization"


@dataclass(frozen=True)
class OrgContext:
    """Who is calling, in which organization, with which role."""

    organization: Organization
    user: User
    role: str
    token: ApiToken | None

    def has_role(self, role: str) -> bool:
        return ROLE_RANK[Role(self.role)] >= ROLE_RANK[Role(role)]


def resolve_org(request: Request) -> OrgContext:
    """Organization of the token, or the `X-Organization` slug, or the user's first one."""
    user = request.user
    token = request.auth if isinstance(request.auth, ApiToken) else None
    slug = request.headers.get(ORG_HEADER)
    memberships = Membership.objects.select_related("organization").filter(user=user)
    if token is not None:
        if slug and slug != token.organization.slug:
            raise exceptions.PermissionDenied("the token belongs to another organization")
        memberships = memberships.filter(organization=token.organization)
    elif slug:
        memberships = memberships.filter(organization__slug=slug)
    membership = memberships.order_by("created_at").first()
    if membership is None:
        raise exceptions.PermissionDenied("not a member of this organization")
    return OrgContext(membership.organization, user, membership.role, token)


class ApiView(APIView):
    """Problem+json errors, cursor pages and `require(role, scope)` for every v1 view."""

    def get_exception_handler(self) -> Callable[[Exception, dict[str, Any]], Response | None]:
        return problem_exception_handler

    @cached_property
    def ctx(self) -> OrgContext:
        return resolve_org(self.request)

    def require(self, role: str, scope: str) -> OrgContext:
        """403 unless the caller has at least `role`; tokens also need `scope`."""
        ctx = self.ctx
        if not ctx.has_role(role):
            raise exceptions.PermissionDenied(f"requires role {role} or higher")
        if ctx.token is not None and not ctx.token.has_scope(scope):
            raise exceptions.PermissionDenied(f"the token lacks scope {scope}")
        return ctx

    def paginate(
        self, queryset: QuerySet[Any], serialize: Callable[[Any], dict[str, Any]], page=CursorPage
    ) -> Response:
        paginator = page()
        rows = paginator.paginate_queryset(queryset, self.request, view=self)
        return paginator.get_paginated_response([serialize(row) for row in rows or []])
