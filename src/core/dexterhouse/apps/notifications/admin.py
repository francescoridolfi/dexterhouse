# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin

from dexterhouse.apps.notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "user", "project", "created_at", "read_at", "emailed_at")
    list_filter = ("kind",)
    search_fields = ("title", "user__username")
    raw_id_fields = ("user", "project", "gate", "organization")
