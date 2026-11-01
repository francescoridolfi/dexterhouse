# SPDX-License-Identifier: AGPL-3.0-or-later
"""Installed processes: the built-in packages under `BUILTIN_DIR/processes`.

The packages app (E-07) adds marketplace and local processes; until then a process is
installed iff its built-in package validates with `dexterhouse-schema`.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import structlog
from django.conf import settings

from dexterhouse_schema import Process, validate_package

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class InstalledProcess:
    name: str
    version: str
    process: Process
    requirements: dict[str, list[str]]
    """Inputs the project must provide (e.g. `stack`), see `Process.brief_requirements`."""


@lru_cache(maxsize=4)
def _scan(root: Path) -> dict[str, InstalledProcess]:
    found: dict[str, InstalledProcess] = {}
    for path in sorted((root / "processes").glob("*/process.yaml")):
        report = validate_package(path.parent)
        process = report.models.get("process.yaml")
        if not report.ok or not isinstance(process, Process):
            logger.error("workflows.builtin_invalid", path=str(path.parent), errors=report.errors)
            continue
        found[process.name] = InstalledProcess(
            process.name, process.version, process, process.brief_requirements()
        )
    return found


def installed_processes() -> dict[str, InstalledProcess]:
    return _scan(Path(settings.BUILTIN_DIR))


def get_process(name: str) -> InstalledProcess | None:
    return installed_processes().get(name)
