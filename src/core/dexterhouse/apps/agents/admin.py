# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin

from dexterhouse.apps.agents.models import AgentInstance, AgentTurn, ToolCall


@admin.register(AgentInstance)
class AgentInstanceAdmin(admin.ModelAdmin):
    list_display = ["display_name", "role", "project_id", "model_profile", "status", "source"]
    list_filter = ["role", "status", "source"]


class ToolCallInline(admin.TabularInline):
    model = ToolCall
    extra = 0
    fields = ["seq", "tool", "status", "allowed", "denied_reason", "duration_ms"]
    readonly_fields = fields
    can_delete = False


@admin.register(AgentTurn)
class AgentTurnAdmin(admin.ModelAdmin):
    """Debug view of a turn: what the agent knew (`context_manifest`) and what it did."""

    list_display = ["purpose", "agent_instance", "status", "tool_calls_count", "cost", "created_at"]
    list_filter = ["status", "error_code"]
    search_fields = ["purpose"]
    inlines = [ToolCallInline]
    readonly_fields = ["context_manifest", "messages", "output", "inputs", "tool_specs"]
