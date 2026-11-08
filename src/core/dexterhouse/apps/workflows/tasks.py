# SPDX-License-Identifier: AGPL-3.0-or-later
"""Celery tasks: load the id, call the service (coding standards).

`run_step` is routed to the `agents` queue (settings `CELERY_TASK_ROUTES`): with
`AgentsTurnRunner` it runs the whole agent turn, minutes long, which must not hold up the
short tasks of `default` (`reconcile`, events, memory indexing).
"""

from celery import shared_task

from dexterhouse.apps.workflows import reminders
from dexterhouse.apps.workflows.engine import common, steps


@shared_task(name=common.RUN_STEP_TASK, acks_late=True)
def run_step(step_run_id: str) -> None:
    steps.run_step(step_run_id)


@shared_task(name="dexterhouse.apps.workflows.tasks.reconcile")
def reconcile() -> int:
    return steps.reconcile()


@shared_task(name="dexterhouse.apps.workflows.tasks.remind_gates")
def remind_gates() -> int:
    return reminders.remind_gates()
