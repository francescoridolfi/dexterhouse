# SPDX-License-Identifier: AGPL-3.0-or-later
"""Celery tasks: load the id, call the service (coding standards). Queue `default`."""

from celery import shared_task

from dexterhouse.apps.workflows.engine import steps


@shared_task(name="dexterhouse.apps.workflows.tasks.run_step", acks_late=True)
def run_step(step_run_id: str) -> None:
    steps.run_step(step_run_id)


@shared_task(name="dexterhouse.apps.workflows.tasks.reconcile")
def reconcile() -> int:
    return steps.reconcile()
