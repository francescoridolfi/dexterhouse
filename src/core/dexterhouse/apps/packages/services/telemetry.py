# SPDX-License-Identifier: AGPL-3.0-or-later
"""Opt-in install telemetry (CD-026, infra/marketplace_detail.md "Telemetria opt-in").

After a successful install of a registry package, and only if the installing organization
set `settings.telemetry = true` (default false) and `MARKETPLACE_URL` is configured, the
core posts `{package, version, core_version, instance_hash}` to
`{MARKETPLACE_URL}/api/v1/installs`. `instance_hash = sha256(installation_id + "YYYY-MM")`:
the installation id is random, generated once in `PACKAGES_DIR/.instance/installation_id`
and never sent, so the hash changes every month and cannot be linked across months.
No IP or user data is sent by the core; failures are only logged.
"""

import contextlib
import hashlib
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx2
import structlog
from django.conf import settings

from dexterhouse import __version__
from dexterhouse.apps.packages.models import (
    InstallStatus,
    PackageInstall,
    PackageSource,
    PackageVersion,
)

logger = structlog.get_logger(__name__)
POST_TIMEOUT_S = 3.0


def _id_file() -> Path:
    return Path(settings.PACKAGES_DIR) / ".instance" / "installation_id"


def installation_id() -> str:
    """The random id of this installation, created on first use (safe across processes)."""
    path = _id_file()
    with contextlib.suppress(OSError):
        if value := path.read_text(encoding="utf-8").strip():
            return value
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{uuid.uuid4().hex}.tmp")
    tmp.write_text(uuid.uuid4().hex, encoding="utf-8")
    try:
        os.link(tmp, path)  # atomic: the first process wins, the others read its id
    except FileExistsError:
        pass
    finally:
        tmp.unlink(missing_ok=True)
    return path.read_text(encoding="utf-8").strip()


def instance_hash(now: datetime | None = None) -> str:
    month = (now or datetime.now(UTC)).strftime("%Y-%m")
    return hashlib.sha256(f"{installation_id()}{month}".encode()).hexdigest()


def enabled(version: PackageVersion) -> bool:
    organization = version.package.organization
    return bool(
        settings.MARKETPLACE_URL
        and version.package.source == PackageSource.MARKETPLACE
        and organization is not None
        and (organization.settings or {}).get("telemetry") is True
    )


def report_install(version: PackageVersion) -> bool:
    """Post one anonymous install; True when sent. No-op unless enabled; never raises."""
    if not enabled(version):
        return False
    url = f"{settings.MARKETPLACE_URL.rstrip('/')}/api/v1/installs"
    payload = {
        "package": version.package.name,
        "version": version.version,
        "core_version": __version__,
    }
    try:
        payload["instance_hash"] = instance_hash()
        httpx2.post(url, json=payload, timeout=POST_TIMEOUT_S).raise_for_status()
    except (httpx2.HTTPError, OSError) as exc:
        logger.warning("packages.telemetry_failed", url=url, error=str(exc))
        return False
    logger.info("packages.telemetry_sent", package=payload["package"], version=version.version)
    return True


def reported(install: PackageInstall) -> PackageInstall:
    """`installer.run_install` hook: report a completed install, return it unchanged."""
    if install.status == InstallStatus.INSTALLED and install.package_version_id:
        report_install(install.package_version)
    return install
