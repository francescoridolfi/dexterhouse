# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from dexterhouse.apps.notifications.api import views

urlpatterns = [
    path("notifications", views.NotificationListView.as_view(), name="notification-list"),
    path(
        "notifications/unread_count",
        views.UnreadCountView.as_view(),
        name="notification-unread-count",
    ),
    path(
        "notifications/read",
        views.NotificationReadAllView.as_view(),
        name="notification-read-all",
    ),
    path(
        "notifications/<uuid:notification_id>/read",
        views.NotificationReadView.as_view(),
        name="notification-read",
    ),
]
