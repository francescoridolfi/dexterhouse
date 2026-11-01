# SPDX-License-Identifier: AGPL-3.0-or-later
"""Built-in packages go through the installer too (dogfooding, F-007).

`sync_builtin` installs every folder of `BUILTIN_DIR/{agents,tools,processes}` as a global
package with source `builtin` (`manage.py packages sync-builtin`, run by the compose
`migrate` service at every start, so an image upgrade updates them). Unchanged folders
(same tree hash) are skipped; a built-in that disappeared from the image is removed, or
only disabled while active projects use it.
"""

from dataclasses import dataclass, field
from pathlib import Path

import structlog
import yaml
from django.conf import settings
from django.db import connection, transaction

from dexterhouse.apps.packages.models import InstallStatus, Package, PackageSource
from dexterhouse.apps.packages.services import catalog, store
from dexterhouse.apps.packages.services.installer import install

logger = structlog.get_logger(__name__)
#: Tools first: an agent's required permissions are resolved against the installed tools.
FOLDERS = ("tools", "agents", "processes")
_LOCK_ID = 7_007_001  # pg advisory lock: one sync at a time


@dataclass
class SyncResult:
    installed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    rejected: dict[str, list[str]] = field(default_factory=dict)
    removed: list[str] = field(default_factory=list)


def builtin_folders(base: Path | None = None) -> list[Path]:
    root = Path(base or settings.BUILTIN_DIR)
    return [
        path
        for folder in FOLDERS
        if (root / folder).is_dir()
        for path in sorted((root / folder).iterdir())
        if (path / "dexterhouse.yaml").is_file()
    ]


def _manifest_name(root: Path) -> str:
    try:
        data = yaml.safe_load((root / "dexterhouse.yaml").read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeDecodeError):
        return root.name
    return str(data.get("name", root.name)) if isinstance(data, dict) else root.name


def _unchanged(name: str, sha: str) -> bool:
    package = (
        Package.objects.filter(
            organization__isnull=True, name=name, source=PackageSource.BUILTIN, deleted_at=None
        )
        .select_related("enabled_version")
        .first()
    )
    version = package.enabled_version if package else None
    return bool(version and version.sha256 == sha and Path(version.install_path).is_dir())


def sync_builtin(base: Path | None = None) -> SyncResult:
    """Install new or changed built-in folders; remove built-ins no longer shipped."""
    result = SyncResult()
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_LOCK_ID])
        seen: set[str] = set()
        for root in builtin_folders(base):
            name = _manifest_name(root)
            seen.add(name)
            if _unchanged(name, store.tree_hash(root)):
                result.unchanged.append(name)
                continue
            done = install(organization=None, source=str(root), builtin=True)
            if done.status == InstallStatus.INSTALLED:
                result.installed.append(name)
            else:
                result.rejected[name] = list(done.errors)
                logger.error("packages.builtin_invalid", path=str(root), errors=done.errors)
        for package in Package.objects.filter(
            organization__isnull=True, source=PackageSource.BUILTIN, deleted_at=None
        ).exclude(name__in=seen):
            _retire(package)
            result.removed.append(package.name)
    return result


def _retire(package: Package) -> None:
    from dexterhouse.apps.packages.services.lifecycle import disable, remove

    if catalog.projects_using_package(package):
        if package.enabled_version_id:
            disable(package, reason="no longer shipped with the core")
        return
    remove(package, reason="no longer shipped with the core")


def ensure_builtin() -> None:
    """Sync the built-ins if the database has none (fresh database, flushed test database)."""
    if not Package.objects.filter(source=PackageSource.BUILTIN).exists():
        sync_builtin()
