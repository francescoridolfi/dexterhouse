# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from dexterhouse.apps.accounts.api import views

urlpatterns = [
    path("auth/csrf", views.CsrfView.as_view(), name="auth-csrf"),
    path("auth/login", views.LoginView.as_view(), name="auth-login"),
    path("auth/logout", views.LogoutView.as_view(), name="auth-logout"),
    path("auth/me", views.MeView.as_view(), name="auth-me"),
    path("organization", views.OrganizationView.as_view(), name="organization"),
    path("organization/members", views.MembersView.as_view(), name="organization-members"),
]
