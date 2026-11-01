# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST v1: project events for the timeline and the replay (events_ws.md)."""

import uuid

from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from rest_framework.request import Request
from rest_framework.response import Response

from dexterhouse.apps.events.models import Event
from dexterhouse.apps.events.services.publisher import to_envelope
from dexterhouse.apps.projects.api.views import READ, get_project
from dexterhouse.common.api import ApiView
from dexterhouse.common.api.pagination import CursorPage
from dexterhouse.common.errors import ValidationFailedError


class EventPage(CursorPage):
    """Oldest first, up to 1 000 per page (replay)."""

    ordering = ("created_at", "id")
    max_page_size = 1_000


class RecentEventPage(EventPage):
    """`?order=desc`: newest first (the live log loads the latest page)."""

    ordering = ("-created_at", "-id")


def event_json(row: Event) -> dict[str, object]:
    return to_envelope(row).model_dump(mode="json")


def _when(name: str, value: str):
    parsed = parse_datetime(value)
    if parsed is None:
        raise ValidationFailedError(
            f"{name} must be an ISO 8601 datetime", [{"field": name, "message": "datetime"}]
        )
    return parsed


class ProjectEventsView(ApiView):
    """`?types=a,b&actor=<uuid|agent|user|system>&agent=<uuid>&phase=<id>&from=&to=&order=desc`."""

    def get(self, request: Request, project_id: uuid.UUID) -> Response:
        project = get_project(self.require(*READ), project_id)
        rows = Event.objects.filter(project_id=project.id)
        params = request.query_params
        if value := params.get("types"):
            rows = rows.filter(type__in=[t for t in value.split(",") if t])
        if value := params.get("actor"):
            if value in ("agent", "user", "system"):
                rows = rows.filter(actor_type=value)
            else:
                rows = rows.filter(actor_id=value)
        if value := params.get("agent"):
            rows = rows.filter(payload__agent_id=value)
        if value := params.get("phase"):
            rows = rows.filter(payload__phase_id=value)
        if value := params.get("from"):
            rows = rows.filter(created_at__gte=_when("from", value))
        if value := params.get("to"):
            rows = rows.filter(created_at__lte=_when("to", value))
        page = RecentEventPage if params.get("order") == "desc" else EventPage
        return self.paginate(rows, event_json, page=page)


class ProjectEventsSummaryView(ApiView):
    def get(self, request: Request, project_id: uuid.UUID) -> Response:
        project = get_project(self.require(*READ), project_id)
        rows = Event.objects.filter(project_id=project.id)
        by_type = rows.values("type").annotate(n=Count("id")).order_by("type")
        by_actor = (
            rows.exclude(actor_id=None)
            .values("actor_id", "actor_name")
            .annotate(n=Count("id"))
            .order_by("-n")
        )
        return Response(
            {
                "total": rows.count(),
                "by_type": {r["type"]: r["n"] for r in by_type},
                "by_actor": [
                    {"id": str(r["actor_id"]), "name": r["actor_name"], "count": r["n"]}
                    for r in by_actor
                ],
            }
        )


class EventDetailView(ApiView):
    def get(self, request: Request, event_id: uuid.UUID) -> Response:
        ctx = self.require(*READ)
        row = get_object_or_404(Event, pk=event_id, organization_id=ctx.organization.id)
        return Response(event_json(row))
