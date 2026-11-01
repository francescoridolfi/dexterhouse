# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from dexterhouse.apps.observability.api import views

urlpatterns = [
    path("projects/<uuid:project_id>/costs", views.ProjectCostsView.as_view(), name="costs"),
    path(
        "projects/<uuid:project_id>/llm-calls",
        views.ProjectLLMCallsView.as_view(),
        name="llm-calls",
    ),
    path(
        "projects/<uuid:project_id>/estimate",
        views.ProjectEstimateView.as_view(),
        name="project-estimate",
    ),
    path("estimate", views.EstimateView.as_view(), name="estimate"),
    path("organization/budget", views.OrganizationBudgetView.as_view(), name="org-budget"),
    path("organization/usage", views.OrganizationUsageView.as_view(), name="org-usage"),
]
