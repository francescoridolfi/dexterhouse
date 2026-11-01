# SPDX-License-Identifier: AGPL-3.0-or-later
"""Callbacks of the runner (`core-callbacks`, CD-021) and the workspace jobs.

The callback task names are the protocol's (`core.runner.*`); they only validate the
payload and call the service, which writes the events: the core is their only writer.
"""

from typing import Any

from celery import shared_task

from dexterhouse_schema.runner import Heartbeat, SecretsBlocked, WorkspaceChanged


@shared_task(name="core.runner.workspace_changed")
def workspace_changed(payload: dict[str, Any]) -> None:
    from dexterhouse.apps.workspaces import services

    services.apply_changed(WorkspaceChanged.model_validate(payload))


@shared_task(name="core.runner.heartbeat")
def heartbeat(payload: dict[str, Any]) -> None:
    from dexterhouse.apps.workspaces import services

    services.apply_heartbeat(Heartbeat.model_validate(payload))


@shared_task(name="core.runner.secrets_blocked")
def secrets_blocked(payload: dict[str, Any]) -> None:
    from dexterhouse.apps.workspaces import events

    events.secrets_blocked(SecretsBlocked.model_validate(payload))


@shared_task(name="dexterhouse.apps.workspaces.tasks.cleanup")
def cleanup() -> dict[str, int]:
    from dexterhouse.apps.workspaces import grants, services

    counts = services.cleanup()
    counts["grants"] = grants.purge()
    return counts


@shared_task(name="dexterhouse.apps.workspaces.tasks.deliver")
def deliver(project_id: str, phase_run_id: str) -> str:
    from dexterhouse.apps.workspaces import delivery

    return delivery.deliver(project_id, phase_run_id)
