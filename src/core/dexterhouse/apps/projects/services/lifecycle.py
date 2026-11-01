# SPDX-License-Identifier: AGPL-3.0-or-later
"""User operations on a project's lifecycle: start, pause, resume, retry, archive."""

from django.db import transaction

from dexterhouse.apps.accounts.models import User
from dexterhouse.apps.projects.models import Project, ProjectStatus
from dexterhouse.apps.projects.services.actors import emit, user_actor
from dexterhouse.apps.projects.services.transitions import transition
from dexterhouse.apps.projects.services.validation import validate_for_start
from dexterhouse.apps.workflows.engine import common, start
from dexterhouse.apps.workflows.models import Gate, GateStatus
from dexterhouse.apps.workflows.registry import get_process
from dexterhouse.common.errors import InvalidTransitionError, ValidationFailedError


def start_project(project_id, user: User) -> Project:
    """draft -> running after validation; creates and starts the ProcessRun."""
    with transaction.atomic():
        project, run = common.lock(project_id)
        if project.status != ProjectStatus.DRAFT:
            raise InvalidTransitionError(f"project cannot start from {project.status}")
        errors = validate_for_start(project)
        if errors:
            raise ValidationFailedError("the project cannot start", errors)
        installed = get_process(project.process_name)
        run = start.create_run(project, installed.process)
        run.project = project
        transition(project, ProjectStatus.RUNNING)
        emit(project, "project.started", {"process_run_id": run.id}, actor=user_actor(user))
        start.start_run(run)
    return project


def pause_project(project_id, user: User) -> Project:
    with transaction.atomic():
        project, _run = common.lock(project_id)
        transition(project, ProjectStatus.PAUSED)
        emit(project, "project.paused", actor=user_actor(user))
    return project


def resume_project(project_id, user: User) -> Project:
    """paused -> running, or waiting when a gate is still open."""
    with transaction.atomic():
        project, run = common.lock(project_id)
        if project.status != ProjectStatus.PAUSED:
            raise InvalidTransitionError(f"project cannot resume from {project.status}")
        if Gate.objects.filter(project=project, status=GateStatus.OPEN).exists():
            transition(project, ProjectStatus.WAITING, waiting_reason="gate")
        else:
            transition(project, ProjectStatus.RUNNING)
        emit(project, "project.resumed", {"reason": "user"}, actor=user_actor(user))
        if run is not None:
            start.resume_run(run)
    return project


def retry_project(project_id, user: User) -> Project:
    with transaction.atomic():
        project, run = common.lock(project_id)
        if project.status != ProjectStatus.FAILED or run is None:
            raise InvalidTransitionError(f"project cannot be retried from {project.status}")
        transition(project, ProjectStatus.RUNNING)
        phase_id = start.retry_run(run)
        emit(project, "project.retried", {"from_phase_id": phase_id}, actor=user_actor(user))
    return project


def archive_project(project_id, user: User) -> Project:
    """Soft delete (`archived`, `deleted_at`); events stay for retention."""
    with transaction.atomic():
        project, run = common.lock(project_id)
        transition(project, ProjectStatus.ARCHIVED)
        if run is not None:
            start.cancel_run(run)
        # Workspace destruction is a runner operation (E-05).
        emit(project, "project.archived", actor=user_actor(user))
    return project
