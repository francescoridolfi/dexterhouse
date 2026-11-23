# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST v1 context documents (docs/specs/context-documents.md, section API)."""

import uuid
from typing import Any

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import exceptions, status
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from dexterhouse.apps.accounts.models import Role
from dexterhouse.apps.projects.api.views import ADMIN, READ, WRITE, get_project
from dexterhouse.apps.projects.models import Artifact, ArtifactKind
from dexterhouse.apps.projects.services import context
from dexterhouse.common.api import ApiView, OrgContext
from dexterhouse.common.errors import ValidationFailedError

META = (
    "filename",
    "title",
    "mime",
    "size",
    "sha256",
    "status",
    "error",
    "active",
    "pages",
    "chars",
    "truncated",
    "change_request",
    "uploaded_by",
)


def document_json(doc: Artifact, *, content: bool = False) -> dict[str, Any]:
    data = doc.data or {}
    out = {
        "id": str(doc.id),
        "project": str(doc.project_id),
        "name": doc.name,
        "version": doc.version,
        **{key: data.get(key) for key in META},
        "created_at": doc.created_at.isoformat().replace("+00:00", "Z"),
    }
    if content:
        out["content"] = doc.content
    return out


def _document(ctx: OrgContext, doc_id: uuid.UUID) -> Artifact:
    rows = Artifact.objects.filter(
        project__organization=ctx.organization, kind=ArtifactKind.CONTEXT
    ).select_related("project")
    return get_object_or_404(rows, pk=doc_id)


class ContextListView(ApiView):
    parser_classes = (MultiPartParser,)

    def get(self, request: Request, project_id: uuid.UUID) -> Response:
        project = get_project(self.require(*READ), project_id)
        everything = request.query_params.get("all") in {"1", "true"}
        docs = context.latest_documents(project, include_inactive=everything)
        return Response({"results": [document_json(d) for d in docs], "next": None})

    def post(self, request: Request, project_id: uuid.UUID) -> Response:
        ctx = self.require(*WRITE)
        project = get_project(ctx, project_id)
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationFailedError(
                "a file is required", [{"field": "file", "message": "required"}]
            )
        change_request = request.data.get("change_request") or None
        try:
            change_request = uuid.UUID(change_request) if change_request else None
        except ValueError:
            raise ValidationFailedError(
                "invalid change request", [{"field": "change_request", "message": "not a uuid"}]
            ) from None
        doc = context.add_document(
            project,
            ctx.user,
            filename=upload.name or "document",
            content=upload.read(),
            title=str(request.data.get("title") or ""),
            change_request_id=change_request,
        )
        return Response(document_json(doc), status=status.HTTP_202_ACCEPTED)


class ContextDetailView(ApiView):
    def get(self, request: Request, doc_id: uuid.UUID) -> Response:
        return Response(document_json(_document(self.require(*READ), doc_id), content=True))

    def delete(self, request: Request, doc_id: uuid.UUID) -> Response:
        """Admins deactivate any document, members the ones they uploaded."""
        ctx = self.require(*WRITE)
        doc = _document(ctx, doc_id)
        own = (doc.data or {}).get("uploaded_by") == str(ctx.user.id)
        if not own and not ctx.has_role(Role.ADMIN):
            self.require(*ADMIN)
        done = context.deactivate_document(doc.project, ctx.user, doc.name)
        return Response(document_json(done))


class ContextDownloadView(ApiView):
    def get(self, request: Request, doc_id: uuid.UUID) -> FileResponse:
        doc = _document(self.require(*READ), doc_id)
        data = doc.data or {}
        path = context.stored_path(doc.project_id, data.get("sha256", ""))
        if not path.is_file():
            raise exceptions.NotFound("the original file is no longer stored")
        return FileResponse(
            path.open("rb"),
            as_attachment=True,
            filename=data.get("filename") or doc.name.removeprefix(context.PREFIX),
            content_type=data.get("mime") or "application/octet-stream",
        )
