# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST v1: change requests (docs/specs/change-requests.md, API)."""

import uuid
from decimal import Decimal
from typing import Any, ClassVar

from django.db.models import Sum
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response

from dexterhouse.apps.gateway.models import LLMCall
from dexterhouse.apps.projects.api.views import ADMIN, READ, WRITE, get_project
from dexterhouse.apps.projects.models import ChangeRequest
from dexterhouse.apps.projects.services import change_requests as service
from dexterhouse.common.api import ApiView, OrgContext
from dexterhouse.common.api.pagination import AscendingCursorPage


class ChangeRequestInput(serializers.Serializer):
    title = serializers.CharField(max_length=120)
    body = serializers.CharField(max_length=20_000)
    budget = serializers.DecimalField(
        max_digits=12, decimal_places=6, min_value=Decimal(0), required=False
    )


def _ts(value: Any) -> str | None:
    return value.isoformat() if value else None


def cost_of(cr: ChangeRequest) -> Decimal:
    """What the CR's iteration has spent so far (LLM calls of its run's turns)."""
    if cr.process_run_id is None:
        return Decimal(0)
    rows = LLMCall.objects.filter(agent_turn__phase_run__process_run_id=cr.process_run_id)
    return rows.aggregate(c=Sum("cost"))["c"] or Decimal(0)


def change_request_json(cr: ChangeRequest) -> dict[str, Any]:
    run = cr.process_run
    return {
        "id": str(cr.id),
        "project": str(cr.project_id),
        "number": cr.number,
        "label": cr.label,
        "title": cr.title,
        "body": cr.body,
        "budget": str(cr.budget),
        "cost": str(cost_of(cr)),
        "status": cr.status,
        "iteration": run.iteration if run else None,
        "process_run": str(run.id) if run else None,
        "created_by": cr.created_by.get_username(),
        "created_at": _ts(cr.created_at),
        "started_at": _ts(cr.started_at),
        "completed_at": _ts(cr.completed_at),
    }


def get_change_request(ctx: OrgContext, cr_id: uuid.UUID) -> ChangeRequest:
    rows = ChangeRequest.objects.filter(project__organization=ctx.organization)
    return get_object_or_404(rows.select_related("project", "created_by", "process_run"), pk=cr_id)


class ChangeRequestListView(ApiView):
    def get(self, request: Request, project_id: uuid.UUID) -> Response:
        project = get_project(self.require(*READ), project_id)
        rows = project.change_requests.select_related("created_by", "process_run")
        if value := request.query_params.get("status"):
            rows = rows.filter(status=value)
        return self.paginate(rows, change_request_json, page=AscendingCursorPage)

    def post(self, request: Request, project_id: uuid.UUID) -> Response:
        ctx = self.require(*WRITE)
        project = get_project(ctx, project_id)
        body = ChangeRequestInput(data=request.data)
        body.is_valid(raise_exception=True)
        cr = service.create_change_request(project, ctx.user, body.validated_data)
        return Response(change_request_json(cr), status=status.HTTP_201_CREATED)


class ChangeRequestDetailView(ApiView):
    def get(self, request: Request, cr_id: uuid.UUID) -> Response:
        return Response(change_request_json(get_change_request(self.require(*READ), cr_id)))

    def patch(self, request: Request, cr_id: uuid.UUID) -> Response:
        ctx = self.require(*WRITE)
        cr = get_change_request(ctx, cr_id)
        body = ChangeRequestInput(data=request.data, partial=True)
        body.is_valid(raise_exception=True)
        service.update_change_request(cr, ctx.user, body.validated_data)
        return Response(change_request_json(get_change_request(ctx, cr_id)))


class ChangeRequestActionView(ApiView):
    """POST /change-requests/{id}/queue|cancel (admin)."""

    action = ""
    services: ClassVar[dict[str, Any]] = {
        "queue": service.queue_change_request,
        "cancel": service.cancel_change_request,
    }

    def post(self, request: Request, cr_id: uuid.UUID) -> Response:
        ctx = self.require(*ADMIN)
        self.services[self.action](get_change_request(ctx, cr_id), ctx.user)
        return Response(change_request_json(get_change_request(ctx, cr_id)))


class ChangeRequestEstimateView(ApiView):
    def get(self, request: Request, cr_id: uuid.UUID) -> Response:
        cr = get_change_request(self.require(*WRITE), cr_id)
        return Response(service.estimate_change_request(cr))
