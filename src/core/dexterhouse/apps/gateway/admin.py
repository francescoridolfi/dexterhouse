# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin

from dexterhouse.apps.gateway.models import LLMCall, ModelProfile


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


@admin.register(ModelProfile)
class ModelProfileAdmin(admin.ModelAdmin):
    """Profile mapping; keys are never stored, only the env var that holds them."""

    list_display = ["organization", "project_id", "profile", "provider", "model", "is_local"]
    list_filter = ["profile", "provider", "is_local"]
