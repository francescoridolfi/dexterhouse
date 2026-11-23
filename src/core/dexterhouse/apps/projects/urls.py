# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from dexterhouse.apps.projects.api import change_requests, views

urlpatterns = [
    path("projects", views.ProjectListView.as_view(), name="project-list"),
    path("projects/<uuid:project_id>", views.ProjectDetailView.as_view(), name="project-detail"),
    *[
        path(
            f"projects/<uuid:project_id>/{action}",
            views.ProjectActionView.as_view(action=action),
            name=f"project-{action}",
        )
        for action in ("start", "pause", "resume", "retry")
    ],
    path(
        "projects/<uuid:project_id>/snapshot",
        views.ProjectSnapshotView.as_view(),
        name="project-snapshot",
    ),
    path(
        "projects/<uuid:project_id>/artifacts",
        views.ArtifactListView.as_view(),
        name="artifact-list",
    ),
    path(
        "artifacts/<uuid:artifact_id>", views.ArtifactDetailView.as_view(), name="artifact-detail"
    ),
    path(
        "artifacts/<uuid:artifact_id>/versions",
        views.ArtifactVersionsView.as_view(),
        name="artifact-versions",
    ),
    path(
        "artifacts/<uuid:artifact_id>/diff", views.ArtifactDiffView.as_view(), name="artifact-diff"
    ),
    path("projects/<uuid:project_id>/notes", views.NoteListView.as_view(), name="note-list"),
    path("notes/<uuid:note_id>", views.NoteDetailView.as_view(), name="note-detail"),
    path(
        "projects/<uuid:project_id>/change-requests",
        change_requests.ChangeRequestListView.as_view(),
        name="change-request-list",
    ),
    path(
        "change-requests/<uuid:cr_id>",
        change_requests.ChangeRequestDetailView.as_view(),
        name="change-request-detail",
    ),
    *[
        path(
            f"change-requests/<uuid:cr_id>/{action}",
            change_requests.ChangeRequestActionView.as_view(action=action),
            name=f"change-request-{action}",
        )
        for action in ("queue", "cancel")
    ],
    path(
        "change-requests/<uuid:cr_id>/estimate",
        change_requests.ChangeRequestEstimateView.as_view(),
        name="change-request-estimate",
    ),
]
