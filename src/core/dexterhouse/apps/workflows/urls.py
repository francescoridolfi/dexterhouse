# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from dexterhouse.apps.workflows.api import views

urlpatterns = [
    path("projects/<uuid:project_id>/phases", views.PhaseListView.as_view(), name="phase-list"),
    path("phases/<uuid:phase_id>", views.PhaseDetailView.as_view(), name="phase-detail"),
    path("phases/<uuid:phase_id>/skip", views.PhaseSkipView.as_view(), name="phase-skip"),
    path("projects/<uuid:project_id>/tasks", views.TaskListView.as_view(), name="task-list"),
    path("tasks/<uuid:task_id>", views.TaskDetailView.as_view(), name="task-detail"),
    path("tasks/<uuid:task_id>/cancel", views.TaskCancelView.as_view(), name="task-cancel"),
    path("gates", views.GateInboxView.as_view(), name="gate-inbox"),
    path("projects/<uuid:project_id>/gates", views.ProjectGatesView.as_view(), name="gate-list"),
    path("gates/<uuid:gate_id>", views.GateDetailView.as_view(), name="gate-detail"),
    path("gates/<uuid:gate_id>/decide", views.GateDecideView.as_view(), name="gate-decide"),
]
