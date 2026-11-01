# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from dexterhouse.apps.accounts.models import ApiToken, Membership, Organization, User


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    autocomplete_fields = ["user"]


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ["slug", "name", "budget_monthly", "spent_month", "created_at"]
    search_fields = ["slug", "name"]
    readonly_fields = ["spent_month", "created_at", "updated_at"]
    inlines = [MembershipInline]


@admin.register(User)
class DexterHouseUserAdmin(UserAdmin):
    pass


@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    """Tokens are created via the API/service (plaintext shown once); admin can only revoke."""

    list_display = ["name", "organization", "user", "scopes", "last_used_at", "expires_at"]
    list_filter = ["organization"]
    readonly_fields = ["token_hash", "last_used_at", "created_at", "updated_at"]
    search_fields = ["name", "user__username"]

    def has_add_permission(self, request) -> bool:  # type: ignore[no-untyped-def]
        return False
