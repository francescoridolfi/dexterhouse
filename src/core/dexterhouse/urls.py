# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularJSONAPIView

from dexterhouse import health, meta
from dexterhouse.apps.observability import metrics

urlpatterns = [
    path("health/live", health.live, name="health-live"),
    path("health/ready", health.ready, name="health-ready"),
    path("metrics", metrics.metrics, name="metrics"),
    path("admin/", admin.site.urls),
    path("", include("dexterhouse.apps.workspaces.urls")),
    path("api/v1/", include("dexterhouse.apps.projects.urls")),
    path("api/v1/", include("dexterhouse.apps.workspaces.api_urls")),
    path("api/v1/", include("dexterhouse.apps.workflows.urls")),
    path("api/v1/", include("dexterhouse.apps.accounts.urls")),
    path("api/v1/", include("dexterhouse.apps.events.urls")),
    path("api/v1/", include("dexterhouse.apps.agents.urls")),
    path("api/v1/", include("dexterhouse.apps.gateway.urls")),
    path("api/v1/", include("dexterhouse.apps.observability.urls")),
    path("api/v1/", include("dexterhouse.apps.notifications.urls")),
    path("api/v1/", include("dexterhouse.apps.packages.urls")),
    path("api/v1/meta", meta.MetaView.as_view(), name="meta"),
    path("api/v1/openapi.json", SpectacularJSONAPIView.as_view(), name="openapi"),
]
