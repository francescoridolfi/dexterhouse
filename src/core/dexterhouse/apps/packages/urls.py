# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from dexterhouse.apps.packages.api import marketplace, views

urlpatterns = [
    path(
        "marketplace/search", marketplace.MarketplaceSearchView.as_view(), name="marketplace-search"
    ),
    path(
        "marketplace/status", marketplace.MarketplaceStatusView.as_view(), name="marketplace-status"
    ),
    path(
        "marketplace/packages/<str:name>",
        marketplace.MarketplacePackageView.as_view(),
        name="marketplace-package",
    ),
    path("packages", views.PackageListView.as_view(), name="package-list"),
    path("packages/validate", views.ValidateView.as_view(), name="package-validate"),
    path(
        "packages/installs/<uuid:install_id>",
        views.InstallDetailView.as_view(),
        name="package-install",
    ),
    path(
        "packages/installs/<uuid:install_id>/consent",
        views.InstallConsentView.as_view(),
        name="package-install-consent",
    ),
    path("packages/<uuid:package_id>", views.PackageDetailView.as_view(), name="package-detail"),
    path(
        "packages/<uuid:package_id>/enable",
        views.PackageEnableView.as_view(),
        name="package-enable",
    ),
    path(
        "packages/<uuid:package_id>/disable",
        views.PackageDisableView.as_view(),
        name="package-disable",
    ),
]
