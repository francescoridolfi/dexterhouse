# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin

from dexterhouse.apps.memory.models import MemoryChunk


@admin.register(MemoryChunk)
class MemoryChunkAdmin(admin.ModelAdmin):
    """Read-only view of the index; chunks are rebuilt from their sources, never edited."""

    list_display = [
        "artifact_name",
        "kind",
        "artifact_version",
        "chunk_index",
        "weight",
        "embedder",
    ]
    list_filter = ["kind", "embedder"]
    search_fields = ["content", "artifact_name"]
    exclude = ["embedding"]

    def has_add_permission(self, request) -> bool:  # type: ignore[no-untyped-def]
        return False

    def has_change_permission(self, request, obj=None) -> bool:  # type: ignore[no-untyped-def]
        return False
