# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from dexterhouse.apps.events.api import views

urlpatterns = [
    path("projects/<uuid:project_id>/events", views.ProjectEventsView.as_view(), name="event-list"),
    path(
        "projects/<uuid:project_id>/events/summary",
        views.ProjectEventsSummaryView.as_view(),
        name="event-summary",
    ),
    path("events/<uuid:event_id>", views.EventDetailView.as_view(), name="event-detail"),
]
