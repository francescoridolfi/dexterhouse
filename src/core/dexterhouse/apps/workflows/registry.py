# SPDX-License-Identifier: AGPL-3.0-or-later
"""Installed processes: the enabled `process` PackageVersions an organization sees.

Built-in processes are installed by `packages sync-builtin` like any other package
(E-07); the definition is the validated `process.yaml` stored in the version. A running
project keeps the process it started with (the process run stores its definition).
"""

import json
import uuid
from dataclasses import dataclass
from functools import lru_cache

from dexterhouse.apps.packages.models import PackageVersion
from dexterhouse.apps.packages.services.catalog import enabled_versions, find_version
from dexterhouse_schema import Process


@dataclass(frozen=True)
class InstalledProcess:
    name: str
    version: str
    process: Process
    requirements: dict[str, list[str]]
    """Inputs the project must provide (e.g. `stack`), see `Process.brief_requirements`."""
    version_id: uuid.UUID | None = None


@lru_cache(maxsize=64)
def _load(version_id: uuid.UUID, _updated: float, definition: str) -> InstalledProcess:
    process = Process.model_validate_json(definition)
    return InstalledProcess(
        process.name, process.version, process, process.brief_requirements(), version_id
    )


def _installed(version: PackageVersion) -> InstalledProcess:
    return _load(version.id, version.updated_at.timestamp(), json.dumps(version.definition))


def installed_processes(organization_id: uuid.UUID | None = None) -> dict[str, InstalledProcess]:
    """Enabled processes by name (global ones, plus the organization's)."""
    return {v.package.name: _installed(v) for v in enabled_versions("process", organization_id)}


def get_process(
    name: str, organization_id: uuid.UUID | None = None, version: str | None = None
) -> InstalledProcess | None:
    """The enabled process `name`, or exactly `version` while it is still installed."""
    found = find_version("process", name, organization_id, version)
    return _installed(found) if found else None
