# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from dexterhouse.apps.gateway.api import views

urlpatterns = [
    path("model-profiles", views.ModelProfilesView.as_view(), name="model-profiles"),
    path("model-profiles/<str:profile>", views.ModelProfileView.as_view(), name="model-profile"),
    path("providers", views.ProvidersView.as_view(), name="providers"),
    path("pricing", views.PricingView.as_view(), name="pricing"),
]
