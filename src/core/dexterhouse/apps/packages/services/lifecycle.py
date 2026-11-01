# SPDX-License-Identifier: AGPL-3.0-or-later
"""Enable, disable, remove, check `compat.core` after a core upgrade, collect old versions.

Disabling hides a package from new hires and new projects; active projects keep the
version they pinned. Removing needs no active project to use it (409 otherwise). Versions
superseded by an upgrade stay `installed` until no active project uses them, then their
files go (`collect_unused`, also run hourly by beat).
"""

import uuid

import structlog
from django.db import transaction
from django.utils import timezone

from dexterhouse.apps.accounts.models import User
from dexterhouse.apps.packages.models import Package, PackageStatus, PackageVersion, VersionStatus
from dexterhouse.apps.packages.services import catalog, store
from dexterhouse.apps.packages.services import index as registry
from dexterhouse.apps.packages.services.events import emit
from dexterhouse.apps.packages.services.installer import core_version, role_holder
from dexterhouse.common.errors import ConflictError, InvalidTransitionError
from dexterhouse_schema.semver import SemanticVersion

logger = structlog.get_logger(__name__)
CORE_INCOMPATIBLE = "core_incompatible"


class PackageInUseError(ConflictError):
    """The package is used by active projects."""


def _emit(package: Package, event_type: str, user: User | None, reason: str | None) -> None:
    emit(
        event_type,
        {"package_id": package.id, "name": package.name, "reason": reason},
        organization_id=package.organization_id,
        user=user,
    )


def disable(package: Package, *, user: User | None = None, reason: str | None = None) -> Package:
    """installed → disabled (`package.disabled`); active projects keep their version."""
    with transaction.atomic():
        package = Package.objects.select_for_update().get(pk=package.pk)
        version = package.enabled_version
        if version is None:
            raise InvalidTransitionError(f"{package.name} is {package.status}, not installed")
        version.status, version.status_reason = VersionStatus.DISABLED, reason or ""
        version.save(update_fields=["status", "status_reason", "updated_at"])
        package.enabled_version = None
        package.status, package.status_reason = PackageStatus.DISABLED, reason or ""
        package.save(update_fields=["enabled_version", "status", "status_reason", "updated_at"])
        _emit(package, "package.disabled", user, reason)
    logger.info("packages.disabled", name=package.name, reason=reason)
    return package


def enable(package: Package, *, user: User | None = None) -> Package:
    """disabled → installed (`package.enabled`) if `compat.core` and the role still fit."""
    with transaction.atomic():
        package = Package.objects.select_for_update().get(pk=package.pk)
        candidates = package.versions.filter(status=VersionStatus.DISABLED)
        version = max(candidates, key=lambda v: SemanticVersion(v.version), default=None)
        if package.enabled_version_id or version is None:
            raise InvalidTransitionError(f"{package.name} is {package.status}, not disabled")
        if not registry.compatible(version.compat_core, core_version()):
            raise ConflictError(
                f"{package.name}@{version.version} requires core {version.compat_core}, "
                f"this is {core_version()}"
            )
        if package.kind == "agent":
            holder = role_holder(
                version.definition.get("role", ""), package.organization_id, package.name
            )
            if holder:
                raise ConflictError(f"role {version.definition['role']} is provided by {holder}")
        version.status, version.status_reason = VersionStatus.INSTALLED, ""
        version.save(update_fields=["status", "status_reason", "updated_at"])
        package.enabled_version = version
        package.status, package.status_reason = PackageStatus.INSTALLED, ""
        package.save(update_fields=["enabled_version", "status", "status_reason", "updated_at"])
        _emit(package, "package.enabled", user, None)
    return package


def remove(package: Package, *, user: User | None = None, reason: str | None = None) -> Package:
    """Remove every version and the files (`package.removed`); 409 if active projects use it.

    Rows stay (soft delete): closed projects keep their `package_version` reference.
    """
    with transaction.atomic():
        package = Package.objects.select_for_update().get(pk=package.pk)
        if package.deleted_at is not None:
            raise InvalidTransitionError(f"{package.name} is already removed")
        using = catalog.projects_using_package(package)
        if using:
            raise PackageInUseError(
                f"{package.name} is used by {len(using)} active project(s)",
                [{"field": "projects", "message": str(p)} for p in using],
            )
        paths = [v.install_path for v in package.versions.exclude(status=VersionStatus.REMOVED)]
        package.versions.update(status=VersionStatus.REMOVED, status_reason="package removed")
        package.enabled_version = None
        package.deleted_at = timezone.now()
        package.status, package.status_reason = PackageStatus.REMOVED, reason or ""
        package.save()
        _emit(package, "package.removed", user, reason)
        transaction.on_commit(lambda: [store.discard(p) for p in paths])
    return package


def check_compat(version: str | None = None) -> list[Package]:
    """Disable every enabled package whose `compat.core` excludes this core (after upgrades).

    Active projects keep the pinned version; the event and the warning tell the admins.
    """
    current = version or core_version()
    disabled = []
    for package in Package.objects.filter(
        deleted_at__isnull=True, enabled_version__isnull=False
    ).select_related("enabled_version"):
        assert package.enabled_version is not None  # nosec B101: filtered above
        if registry.compatible(package.enabled_version.compat_core, current):
            continue
        logger.warning(
            "packages.core_incompatible",
            name=package.name,
            version=package.enabled_version.version,
            compat_core=package.enabled_version.compat_core,
            core=current,
        )
        disabled.append(disable(package, reason=CORE_INCOMPATIBLE))
    return disabled


def collect_unused(package_id: uuid.UUID | None = None) -> list[PackageVersion]:
    """Remove superseded versions (status installed, not enabled) no active project uses."""
    rows = PackageVersion.objects.select_related("package").filter(status=VersionStatus.INSTALLED)
    if package_id:
        rows = rows.filter(package_id=package_id)
    collected = []
    for version in rows:
        if version.package.enabled_version_id == version.id or catalog.projects_using(version):
            continue
        version.status, version.status_reason = VersionStatus.REMOVED, "superseded"
        version.save(update_fields=["status", "status_reason", "updated_at"])
        store.discard(version.install_path)
        collected.append(version)
    return collected
