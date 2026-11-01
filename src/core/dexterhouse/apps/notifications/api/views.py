# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST v1: the caller's notifications (contracts/api/notifications.md, E-06)."""

import uuid
from typing import Any

from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response

from dexterhouse.apps.accounts.models import Role, Scope
from dexterhouse.apps.notifications import services
from dexterhouse.apps.notifications.models import Notification
from dexterhouse.common.api import ApiView

READ = (Role.VIEWER, Scope.PROJECTS_READ)


def _ts(value: Any) -> str | None:
    return value.isoformat() if value else None


def notification_json(note: Notification) -> dict[str, Any]:
    return {
        "id": str(note.id),
        "kind": note.kind,
        "title": note.title,
        "body": note.body,
        "data": note.data,
        "project": str(note.project_id) if note.project_id else None,
        "gate": str(note.gate_id) if note.gate_id else None,
        "read": note.read_at is not None,
        "read_at": _ts(note.read_at),
        "emailed_at": _ts(note.emailed_at),
        "created_at": _ts(note.created_at),
    }


class ReadInput(serializers.Serializer):
    ids = serializers.ListField(child=serializers.UUIDField(), required=False, allow_null=True)


class NotificationListView(ApiView):
    def get(self, request: Request) -> Response:
        ctx = self.require(*READ)
        rows = services.for_user(ctx.user, ctx.organization.id)
        if request.query_params.get("unread") in ("1", "true"):
            rows = rows.filter(read_at__isnull=True)
        if value := request.query_params.get("project"):
            rows = rows.filter(project_id=value)
        return self.paginate(rows, notification_json)


class UnreadCountView(ApiView):
    def get(self, request: Request) -> Response:
        ctx = self.require(*READ)
        rows = services.for_user(ctx.user, ctx.organization.id).filter(read_at__isnull=True)
        return Response({"count": rows.count()})


class NotificationReadView(ApiView):
    def post(self, request: Request, notification_id: uuid.UUID) -> Response:
        ctx = self.require(*READ)
        note = get_object_or_404(
            services.for_user(ctx.user, ctx.organization.id), pk=notification_id
        )
        services.mark_read(ctx.user, ctx.organization.id, [note.id])
        note.refresh_from_db()
        return Response(notification_json(note))


class NotificationReadAllView(ApiView):
    def post(self, request: Request) -> Response:
        ctx = self.require(*READ)
        body = ReadInput(data=request.data)
        body.is_valid(raise_exception=True)
        count = services.mark_read(ctx.user, ctx.organization.id, body.validated_data.get("ids"))
        return Response({"marked": count})
