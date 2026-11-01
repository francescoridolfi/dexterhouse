# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from dexterhouse.apps.workspaces import views

urlpatterns = [
    path("internal/secrets/<uuid:grant_id>", views.secret, name="internal-secret"),
]
