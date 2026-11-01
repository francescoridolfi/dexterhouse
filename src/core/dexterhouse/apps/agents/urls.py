# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from dexterhouse.apps.agents.api import views

urlpatterns = [
    path("projects/<uuid:project_id>/agents", views.ProjectAgentsView.as_view(), name="agents"),
    path("projects/<uuid:project_id>/turns", views.ProjectTurnsView.as_view(), name="turns"),
    path("agents/<uuid:agent_id>", views.AgentDetailView.as_view(), name="agent-detail"),
    path("agents/<uuid:agent_id>/turns", views.AgentTurnsView.as_view(), name="agent-turns"),
    path("turns/<uuid:turn_id>", views.TurnDetailView.as_view(), name="turn-detail"),
]
