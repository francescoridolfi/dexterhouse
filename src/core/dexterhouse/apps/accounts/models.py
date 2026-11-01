# SPDX-License-Identifier: AGPL-3.0-or-later
"""Organization, User, Membership, ApiToken (contracts/data_model/core.md)."""

from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.fields import ArrayField
from django.db import models

from dexterhouse.common.models import BaseModel, new_id


class Role(models.TextChoices):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class Scope(models.TextChoices):
    PROJECTS_READ = "projects:read"
    PROJECTS_WRITE = "projects:write"
    GATES_DECIDE = "gates:decide"
    PACKAGES_MANAGE = "packages:manage"
    EVENTS_READ = "events:read"


class Organization(BaseModel):
    """Root of every tenant-scoped entity (ADR-0015)."""

    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    settings = models.JSONField(default=dict, blank=True)
    budget_monthly = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    spent_month = models.DecimalField(max_digits=12, decimal_places=6, default=0)

    class Meta:
        db_table = "dh_accounts_organization"

    def __str__(self) -> str:
        return self.slug


class User(AbstractUser):
    """Django user with a UUIDv7 primary key."""

    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dh_accounts_user"


class Membership(BaseModel):
    """A user's role inside an organization; `viewer` cannot decide gates."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.MEMBER)

    class Meta:
        db_table = "dh_accounts_membership"
        constraints = [
            models.UniqueConstraint(fields=["user", "organization"], name="dh_membership_unique"),
            models.CheckConstraint(
                condition=models.Q(role__in=Role.values), name="dh_membership_role_valid"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}@{self.organization_id}:{self.role}"


class ApiToken(BaseModel):
    """Bearer token for API/CLI; only the sha256 hash is stored."""

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="api_tokens"
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="api_tokens")
    name = models.CharField(max_length=80)
    token_hash = models.CharField(max_length=128, unique=True, editable=False)
    scopes = ArrayField(models.CharField(max_length=32, choices=Scope.choices), default=list)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "dh_accounts_apitoken"

    def __str__(self) -> str:
        return self.name

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


__all__ = ["ApiToken", "Membership", "Organization", "Role", "Scope", "User"]
