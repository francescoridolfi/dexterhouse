# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin
from django.urls import include, path

from dexterhouse import health

urlpatterns = [
    path("health/live", health.live, name="health-live"),
    path("health/ready", health.ready, name="health-ready"),
    path("admin/", admin.site.urls),
    path("api/v1/", include("dexterhouse.apps.projects.urls")),
    path("api/v1/", include("dexterhouse.apps.workflows.urls")),
]
