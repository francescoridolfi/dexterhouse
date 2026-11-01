# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST v1: projects, artifacts, notes (contracts/api/projects.md)."""

import uuid
from collections.abc import Callable
from typing import ClassVar

from django.db import transaction
from django.db.models import Max, Q, QuerySet
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

from dexterhouse.apps.accounts.models import Role, Scope
from dexterhouse.apps.projects.api.serializers import (
    ArtifactInput,
    NoteInput,
    ProjectInput,
    artifact_json,
    note_json,
    project_json,
)
from dexterhouse.apps.projects.models import Artifact, Note, Project, ProjectStatus
from dexterhouse.apps.projects.services import artifacts, lifecycle, notes, projects
from dexterhouse.apps.projects.services.snapshot import build_snapshot
from dexterhouse.apps.workflows.models import PhaseRun
from dexterhouse.common.api import ApiView, OrgContext
from dexterhouse.common.api.idempotency import idempotent
from dexterhouse.common.errors import ConflictError, ValidationFailedError

READ = (Role.VIEWER, Scope.PROJECTS_READ)
WRITE = (Role.MEMBER, Scope.PROJECTS_WRITE)
ADMIN = (Role.ADMIN, Scope.PROJECTS_WRITE)


def org_projects(ctx: OrgContext) -> QuerySet[Project]:
    return Project.objects.filter(organization=ctx.organization).select_related(
        "organization", "created_by"
    )


def get_project(ctx: OrgContext, project_id: uuid.UUID) -> Project:
    return get_object_or_404(org_projects(ctx), pk=project_id)


class ProjectListView(ApiView):
    def get(self, request: Request) -> Response:
        ctx = self.require(*READ)
        rows = org_projects(ctx)
        params = request.query_params
        if value := params.get("status"):
            rows = rows.filter(status=value)
        else:
            rows = rows.exclude(status=ProjectStatus.ARCHIVED)
        if value := params.get("execution_mode"):
            rows = rows.filter(execution_mode=value)
        if value := params.get("q"):
            rows = rows.filter(Q(name__icontains=value) | Q(brief__icontains=value))
        return self.paginate(rows, project_json)

    @idempotent
    def post(self, request: Request) -> Response:
        ctx = self.require(*WRITE)
        body = ProjectInput(data=request.data)
        body.is_valid(raise_exception=True)
        with transaction.atomic():
            project = projects.create_project(ctx.organization, ctx.user, body.validated_data)
        return Response(project_json(project, detail=True), status=status.HTTP_201_CREATED)


class ProjectDetailView(ApiView):
    def get(self, request: Request, project_id: uuid.UUID) -> Response:
        return Response(project_json(get_project(self.require(*READ), project_id), detail=True))

    def patch(self, request: Request, project_id: uuid.UUID) -> Response:
        ctx = self.require(*WRITE)
        body = ProjectInput(data=request.data, partial=True)
        body.is_valid(raise_exception=True)
        with transaction.atomic():
            project = get_project(ctx, project_id)
            project = Project.objects.select_for_update().get(pk=project.pk)
            projects.update_project(project, ctx.user, body.validated_data)
        return Response(project_json(get_project(ctx, project_id), detail=True))

    def delete(self, request: Request, project_id: uuid.UUID) -> Response:
        ctx = self.require(*ADMIN)
        project = get_project(ctx, project_id)
        lifecycle.archive_project(project.id, ctx.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectActionView(ApiView):
    """POST /projects/{id}/start|pause|resume|retry."""

    action = ""
    roles: ClassVar[dict[str, tuple[str, str]]] = {
        "start": WRITE,
        "pause": WRITE,
        "resume": WRITE,
        "retry": ADMIN,
    }
    services: ClassVar[dict[str, Callable[..., Project]]] = {
        "start": lifecycle.start_project,
        "pause": lifecycle.pause_project,
        "resume": lifecycle.resume_project,
        "retry": lifecycle.retry_project,
    }

    def post(self, request: Request, project_id: uuid.UUID) -> Response:
        ctx = self.require(*self.roles[self.action])
        project = get_project(ctx, project_id)
        self.services[self.action](project.id, ctx.user)
        return Response(project_json(get_project(ctx, project_id), detail=True))


class ProjectSnapshotView(ApiView):
    def get(self, request: Request, project_id: uuid.UUID) -> Response:
        return Response(build_snapshot(get_project(self.require(*READ), project_id)))


class ArtifactListView(ApiView):
    def get(self, request: Request, project_id: uuid.UUID) -> Response:
        project = get_project(self.require(*READ), project_id)
        rows = Artifact.objects.filter(project=project)
        params = request.query_params
        if value := params.get("kind"):
            rows = rows.filter(kind=value)
        if value := params.get("phase_run"):
            rows = rows.filter(phase_run_id=value)
        if value := params.get("q"):
            rows = rows.filter(search=value)
        if params.get("latest") == "true":
            newest = (
                Artifact.objects.filter(project=project)
                .values("kind", "name")
                .annotate(v=Max("version"))
            )
            latest = Q(pk__in=[])
            for item in newest:
                latest |= Q(kind=item["kind"], name=item["name"], version=item["v"])
            rows = rows.filter(latest)
        return self.paginate(rows, artifact_json)

    @idempotent
    def post(self, request: Request, project_id: uuid.UUID) -> Response:
        ctx = self.require(*WRITE)
        body = ArtifactInput(data=request.data)
        body.is_valid(raise_exception=True)
        with transaction.atomic():
            project = Project.objects.select_for_update().get(pk=get_project(ctx, project_id).pk)
            if project.status == ProjectStatus.ARCHIVED:
                raise ConflictError("archived projects cannot change")
            artifact = artifacts.save_artifact(project, **body.validated_data)
        return Response(artifact_json(artifact, content=True), status=status.HTTP_201_CREATED)


def get_artifact(ctx: OrgContext, artifact_id: uuid.UUID) -> Artifact:
    return get_object_or_404(
        Artifact.objects.filter(project__organization=ctx.organization), pk=artifact_id
    )


class ArtifactDetailView(ApiView):
    def get(self, request: Request, artifact_id: uuid.UUID) -> Response:
        return Response(artifact_json(get_artifact(self.require(*READ), artifact_id), content=True))


class ArtifactVersionsView(ApiView):
    def get(self, request: Request, artifact_id: uuid.UUID) -> Response:
        artifact = get_artifact(self.require(*READ), artifact_id)
        return Response({"results": [artifact_json(a) for a in artifacts.versions(artifact)]})


class ArtifactDiffView(ApiView):
    def get(self, request: Request, artifact_id: uuid.UUID) -> Response:
        artifact = get_artifact(self.require(*READ), artifact_id)
        against = request.query_params.get("against", "")
        if not against.isdigit():
            raise ValidationFailedError(
                "against must be a version number", [{"field": "against", "message": "integer"}]
            )
        return Response(
            {
                "from": int(against),
                "to": artifact.version,
                "diff": artifacts.diff(artifact, int(against)),
            }
        )


class NoteListView(ApiView):
    def get(self, request: Request, project_id: uuid.UUID) -> Response:
        project = get_project(self.require(*READ), project_id)
        return self.paginate(
            Note.objects.filter(project=project).select_related("author"), note_json
        )

    @idempotent
    def post(self, request: Request, project_id: uuid.UUID) -> Response:
        ctx = self.require(*WRITE)
        project = get_project(ctx, project_id)
        body = NoteInput(data=request.data)
        body.is_valid(raise_exception=True)
        phase_run = body.validated_data["phase_run"]
        if phase_run == notes.CURRENT:
            phase_run = notes.current_phase_run(project)
        elif phase_run:
            phase_run = uuid.UUID(phase_run)
        if (
            phase_run
            and not PhaseRun.objects.filter(process_run__project=project, pk=phase_run).exists()
        ):
            raise ValidationFailedError(
                "unknown phase run", [{"field": "phase_run", "message": "not in this project"}]
            )
        with transaction.atomic():
            note = notes.add_note(project, ctx.user, body.validated_data["content"], phase_run)
        return Response(note_json(note), status=status.HTTP_201_CREATED)


class NoteDetailView(ApiView):
    def delete(self, request: Request, note_id: uuid.UUID) -> Response:
        ctx = self.require(*WRITE)
        note = get_object_or_404(
            Note.objects.filter(project__organization=ctx.organization), pk=note_id
        )
        notes.delete_note(note)
        return Response(status=status.HTTP_204_NO_CONTENT)
