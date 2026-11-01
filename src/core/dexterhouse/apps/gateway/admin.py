# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin

from dexterhouse.apps.gateway.models import LLMCall


@admin.register(LLMCall)
class LLMCallAdmin(admin.ModelAdmin):
    """Read-only audit of provider calls."""

    list_display = ["created_at", "provider", "model", "profile", "status", "cost", "latency_ms"]
    list_filter = ["provider", "status", "profile"]
    search_fields = ["model", "trace_id"]

    def has_add_permission(self, request) -> bool:  # type: ignore[no-untyped-def]
        return False

    def has_change_permission(self, request, obj=None) -> bool:  # type: ignore[no-untyped-def]
        return False
