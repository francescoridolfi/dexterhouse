# SPDX-License-Identifier: AGPL-3.0-or-later
"""Process run lifecycle driven by the project: start, resume, retry, cancel."""

from django.utils import timezone

from dexterhouse.apps.projects.models import Project
from dexterhouse.apps.projects.services.actors import emit
from dexterhouse.apps.workflows.engine import common, phases
from dexterhouse.apps.workflows.models import (
    PhaseRun,
    PhaseStatus,
    ProcessRun,
    ProcessRunStatus,
)
from dexterhouse.apps.workflows.roles import phase_room
from dexterhouse_schema import Process


def create_run(project: Project, process: Process) -> ProcessRun:
    """`ProcessRun` (pending) with a frozen copy of the definition."""
    return ProcessRun.objects.create(
        project=project,
        process_name=process.name,
        process_version=process.version,
        definition=process.model_dump(mode="json", by_alias=True, exclude_none=True),
    )


def start_run(run: ProcessRun) -> None:
    """pending -> running: `process.started`, one PhaseRun per phase, schedule the first."""
    process = common.process_of(run)
    run.status = ProcessRunStatus.RUNNING
    run.started_at = timezone.now()
    common.save(run, "status", "started_at")
    PhaseRun.objects.bulk_create(
        PhaseRun(process_run=run, phase_id=p.id, position=i, room=phase_room(process, p))
        for i, p in enumerate(process.phases)
    )
    emit(
        run.project,
        "process.started",
        {
            "phases": [
                {"id": p.id, "needs": p.needs, "room": phase_room(process, p)}
                for p in process.phases
            ]
        },
    )
    phases.advance(run)


def resume_run(run: ProcessRun) -> None:
    """After pause/resume or a budget raise: re-dispatch what was waiting."""
    common.sync_waiting(run)
    phases.advance(run)
    common.dispatch_pending(run.project)


def retry_run(run: ProcessRun) -> str:
    """failed -> running from the failed phase; returns its id."""
    failed = PhaseRun.objects.filter(process_run=run, status=PhaseStatus.FAILED).first()
    run.status = ProcessRunStatus.RUNNING
    run.error_code = None
    run.error_detail = None
    run.finished_at = None
    common.save(run, "status", "error_code", "error_detail", "finished_at")
    if failed is not None:
        failed.status = PhaseStatus.RUNNING
        failed.error_code = None
        failed.finished_at = None
        failed.exit_attempts = 0
        common.save(failed, "status", "error_code", "finished_at", "exit_attempts")
    phases.advance(run)
    return failed.phase_id if failed else ""


def cancel_run(run: ProcessRun) -> None:
    common.cancel_process(run)
