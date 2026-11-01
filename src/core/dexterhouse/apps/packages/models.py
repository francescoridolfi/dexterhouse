# SPDX-License-Identifier: AGPL-3.0-or-later
"""Package, PackageVersion and PackageInstall (contracts/data_model/infra.md).

A package with `organization = NULL` is *global*: the built-in packages (synced from
`BUILTIN_DIR`) and the ones an operator installs with the CLI without `--org`. Every
organization sees the global packages plus its own. `PackageInstall` tracks one install
request through `state_machines/package.md` (the API's `install_id`).
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from dexterhouse.apps.accounts.models import Organization
from dexterhouse.common.models import BaseModel


class PackageKind(models.TextChoices):
    AGENT = "agent"
    TOOL = "tool"
    PROCESS = "process"


class PackageSource(models.TextChoices):
    BUILTIN = "builtin"
    MARKETPLACE = "marketplace"
    LOCAL = "local"


class VersionStatus(models.TextChoices):
    AWAITING_CONSENT = "awaiting_consent"
    INSTALLED = "installed"
    DISABLED = "disabled"
    REMOVED = "removed"


class PackageStatus(models.TextChoices):
    """Status of the package as a whole (its enabled version, or why there is none)."""

    AWAITING_CONSENT = "awaiting_consent"
    INSTALLED = "installed"
    DISABLED = "disabled"
    REMOVED = "removed"


class InstallStatus(models.TextChoices):
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    AWAITING_CONSENT = "awaiting_consent"
    INSTALLED = "installed"
    INCOMPATIBLE = "incompatible"
    DECLINED = "declined"
    FAILED = "failed"


class RejectReason(models.TextChoices):
    HASH = "hash"
    SCHEMA = "schema"
    COMPAT = "compat"
    SCAN = "scan"
    DECLINED = "declined"
    FETCH = "fetch"


class Package(BaseModel):
    organization = models.ForeignKey(
        Organization, null=True, blank=True, on_delete=models.CASCADE, related_name="packages"
    )
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=16, choices=PackageKind.choices)
    source = models.CharField(max_length=16, choices=PackageSource.choices)
    source_url = models.CharField(max_length=500, blank=True, default="")
    enabled_version = models.ForeignKey(
        "PackageVersion", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    status = models.CharField(
        max_length=24, choices=PackageStatus.choices, default=PackageStatus.INSTALLED
    )
    status_reason = models.CharField(max_length=200, blank=True, default="")
    latest_available = models.CharField(max_length=32, blank=True, default="")
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "dh_packages_package"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                condition=Q(deleted_at__isnull=True),
                nulls_distinct=False,
                name="dh_package_org_name_live",
            )
        ]

    def __str__(self) -> str:
        return self.name


class PackageVersion(BaseModel):
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name="versions")
    version = models.CharField(max_length=32)
    git_ref = models.CharField(max_length=120, blank=True, default="")
    sha256 = models.CharField(max_length=64)
    manifest = models.JSONField()
    definition = models.JSONField()
    schema = models.SmallIntegerField(default=1)
    compat_core = models.CharField(max_length=64)
    permissions = models.JSONField(default=list, blank=True)
    """`[{id, risk, description}]`: the tool's permissions, or the tools an agent requires."""
    status = models.CharField(max_length=24, choices=VersionStatus.choices)
    status_reason = models.CharField(max_length=200, blank=True, default="")
    consent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    consent_at = models.DateTimeField(null=True, blank=True)
    install_path = models.CharField(max_length=300)

    class Meta:
        db_table = "dh_packages_packageversion"
        constraints = [
            models.UniqueConstraint(fields=["package", "version"], name="dh_pkgversion_unique")
        ]

    def __str__(self) -> str:
        return f"{self.package.name}@{self.version}"

    @property
    def high_risk_permissions(self) -> list[dict[str, str]]:
        return [p for p in self.permissions if p.get("risk") == "high"]


class PackageInstall(BaseModel):
    """One install (or upgrade) request: `GET /packages/installs/{id}`."""

    organization = models.ForeignKey(
        Organization, null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    project = models.ForeignKey(
        "projects.Project", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    source = models.CharField(max_length=16, choices=PackageSource.choices)
    source_url = models.CharField(max_length=500)
    """`git+https://…@ref`, a local path, a built-in folder, or the marketplace name."""
    requested_version = models.CharField(max_length=32, blank=True, default="")
    confirm_permissions = models.JSONField(default=list, blank=True)
    name = models.CharField(max_length=120, blank=True, default="")
    version = models.CharField(max_length=32, blank=True, default="")
    kind = models.CharField(max_length=16, choices=PackageKind.choices, blank=True, default="")
    status = models.CharField(
        max_length=24, choices=InstallStatus.choices, default=InstallStatus.DOWNLOADING
    )
    reason = models.CharField(max_length=16, choices=RejectReason.choices, blank=True, default="")
    errors = models.JSONField(default=list, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    consent_required = models.JSONField(default=list, blank=True)
    package_version = models.ForeignKey(
        PackageVersion, null=True, blank=True, on_delete=models.SET_NULL, related_name="installs"
    )
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "dh_packages_packageinstall"

    def __str__(self) -> str:
        return f"install {self.source_url} ({self.status})"
