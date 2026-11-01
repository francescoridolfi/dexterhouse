# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST v1: costs, LLM calls, estimates, organization budget and usage (F-012, admin.md)."""

import uuid
from datetime import date
from decimal import Decimal

from django.db import transaction
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response

from dexterhouse.apps.accounts.models import Organization, Role, Scope
from dexterhouse.apps.gateway.models import LLMCall
from dexterhouse.apps.observability.services import budget, costs
from dexterhouse.apps.observability.services.estimate import estimate
from dexterhouse.apps.projects.api.views import READ, get_project
from dexterhouse.common.api import ApiView
from dexterhouse.common.errors import ValidationFailedError

ADMIN_READ = (Role.ADMIN, Scope.PROJECTS_READ)
ADMIN_WRITE = (Role.ADMIN, Scope.PROJECTS_WRITE)


def llm_call_json(call: LLMCall) -> dict[str, object]:
    return {
        "id": str(call.id),
        "agent_turn": str(call.agent_turn_id) if call.agent_turn_id else None,
        "provider": call.provider,
        "model": call.model,
        "profile": call.profile,
        "status": call.status,
        "input_tokens": call.input_tokens,
        "output_tokens": call.output_tokens,
        "cached_tokens": call.cached_tokens,
        "cost": str(call.cost) if call.cost is not None else None,
        "price_version": call.price_version,
        "latency_ms": call.latency_ms,
        "error_detail": call.error_detail or None,
        "trace_id": call.trace_id,
        "created_at": call.created_at.isoformat(),
    }


def budget_json(org: Organization) -> dict[str, object]:
    return {
        "currency": "EUR",
        "budget_monthly": str(org.budget_monthly) if org.budget_monthly is not None else None,
        "spent_month": str(org.spent_month),
        "month": costs.month_start().strftime("%Y-%m"),
    }


class ProjectCostsView(ApiView):
    def get(self, request: Request, project_id: uuid.UUID) -> Response:
        return Response(costs.project_costs(get_project(self.require(*READ), project_id)))


class ProjectLLMCallsView(ApiView):
    def get(self, request: Request, project_id: uuid.UUID) -> Response:
        project = get_project(self.require(*READ), project_id)
        rows = LLMCall.objects.filter(project=project)
        for name in ("provider", "status", "agent_turn"):
            if value := request.query_params.get(name):
                rows = rows.filter(**{name: value})
        return self.paginate(rows, llm_call_json)


class ProjectEstimateView(ApiView):
    def get(self, request: Request, project_id: uuid.UUID) -> Response:
        project = get_project(self.require(*READ), project_id)
        return Response(estimate(project.organization_id, project.process_name, len(project.brief)))


class EstimateView(ApiView):
    """`GET /estimate?process=&brief_chars=`: the range shown by the creation form."""

    def get(self, request: Request) -> Response:
        ctx = self.require(*READ)
        process = request.query_params.get("process") or "software-house-default"
        chars = request.query_params.get("brief_chars", "0")
        if not chars.isdigit():
            raise ValidationFailedError(
                "brief_chars must be an integer", [{"field": "brief_chars", "message": "integer"}]
            )
        return Response(estimate(ctx.organization.id, process, int(chars)))


class BudgetInput(serializers.Serializer):
    budget_monthly = serializers.DecimalField(
        max_digits=12, decimal_places=6, min_value=Decimal(0), allow_null=True
    )


class OrganizationBudgetView(ApiView):
    def get(self, request: Request) -> Response:
        return Response(budget_json(self.require(*ADMIN_READ).organization))

    def put(self, request: Request) -> Response:
        ctx = self.require(*ADMIN_WRITE)
        body = BudgetInput(data=request.data)
        body.is_valid(raise_exception=True)
        with transaction.atomic():
            org = Organization.objects.select_for_update().get(pk=ctx.organization.pk)
            org.budget_monthly = body.validated_data["budget_monthly"]
            org.spent_month = costs.organization_month_spend(org.id)
            org.save(update_fields=["budget_monthly", "spent_month", "updated_at"])
        budget.on_org_budget_changed(org)
        return Response(budget_json(org))


class OrganizationUsageView(ApiView):
    def get(self, request: Request) -> Response:
        ctx = self.require(*ADMIN_READ)
        raw = request.query_params.get("month") or costs.month_start().strftime("%Y-%m")
        try:
            year, month = (int(part) for part in raw.split("-"))
            first = date(year, month, 1)
        except ValueError:
            raise ValidationFailedError(
                "month must be YYYY-MM", [{"field": "month", "message": "YYYY-MM"}]
            ) from None
        return Response(costs.organization_usage(ctx.organization, first))
