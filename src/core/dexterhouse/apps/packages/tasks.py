# SPDX-License-Identifier: AGPL-3.0-or-later
"""Celery jobs of the packages app (thin wrappers around services)."""

import uuid

from celery import shared_task

from dexterhouse.apps.packages.services import installer, lifecycle, updates


@shared_task(name="dexterhouse.apps.packages.tasks.run_install")
def run_install(install_id: str) -> str:
    return installer.run_install(uuid.UUID(install_id)).status


@shared_task(name="dexterhouse.apps.packages.tasks.collect_unused")
def collect_unused() -> int:
    return len(lifecycle.collect_unused())


@shared_task(name="dexterhouse.apps.packages.tasks.check_updates")
def check_updates() -> list[str]:
    return updates.check_updates()
