# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from dexterhouse.apps.workspaces import api

urlpatterns = [
    path(f"projects/<uuid:project_id>/code/{name}", view.as_view(), name=f"code-{name}")
    for name, view in (
        ("tree", api.CodeTreeView),
        ("file", api.CodeFileView),
        ("log", api.CodeLogView),
        ("location", api.CodeLocationView),
    )
]
