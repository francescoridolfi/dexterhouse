# SPDX-License-Identifier: AGPL-3.0-or-later
"""`package.update_available`: compare installed registry packages with the index (beat)."""

import structlog

from dexterhouse.apps.packages.models import Package, PackageSource
from dexterhouse.apps.packages.services import index as registry
from dexterhouse.apps.packages.services.events import emit
from dexterhouse.apps.packages.services.installer import core_version
from dexterhouse_schema.semver import SemanticVersion

logger = structlog.get_logger(__name__)


def check_updates() -> list[str]:
    """Emit `package.update_available` once per newer version listed in the registry."""
    try:
        snapshot = registry.get_index(refresh=True)
    except registry.IndexUnavailableError as exc:
        logger.warning("packages.update_check_skipped", error=str(exc))
        return []
    if snapshot is None:
        return []
    found = []
    for package in Package.objects.filter(
        source=PackageSource.MARKETPLACE, deleted_at__isnull=True, enabled_version__isnull=False
    ).select_related("enabled_version"):
        entry = snapshot.get(package.name)
        current = package.enabled_version
        if entry is None or current is None or package.latest_available == entry.latest:
            continue
        if not SemanticVersion(entry.latest) > SemanticVersion(current.version):
            continue
        latest = entry.versions[-1]
        emit(
            "package.update_available",
            {
                "package_id": package.id,
                "name": package.name,
                "current": current.version,
                "latest": entry.latest,
                "compat_ok": registry.compatible(latest.compat_core, core_version()),
            },
            organization_id=package.organization_id,
        )
        package.latest_available = entry.latest
        package.save(update_fields=["latest_available", "updated_at"])
        found.append(f"{package.name}@{entry.latest}")
    return found
