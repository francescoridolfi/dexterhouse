# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST v1, read-only: the project's code (`/projects/{id}/code/...`, docs/api.md).

Same permissions as the project itself (viewer role, `projects:read` scope). Reads at a
commit id are immutable, so their responses may be cached privately by the browser.
"""

import re
import uuid

from rest_framework.request import Request
from rest_framework.response import Response

from dexterhouse.apps.projects.api.views import READ, get_project
from dexterhouse.apps.workspaces import code
from dexterhouse.common.api import ApiView
from dexterhouse.common.errors import ValidationFailedError

_SHA = re.compile(r"^[0-9a-f]{40}$")
MAX_LOG = 200


def _cached(response: Response, ref: str) -> Response:
    if _SHA.match(ref):
        response["Cache-Control"] = "private, max-age=3600, immutable"
    return response


class CodeTreeView(ApiView):
    def get(self, request: Request, project_id: uuid.UUID) -> Response:
        project = get_project(self.require(*READ), project_id)
        ref = request.query_params.get("ref") or "HEAD"
        return _cached(Response(code.tree(project, ref)), ref)


class CodeFileView(ApiView):
    def get(self, request: Request, project_id: uuid.UUID) -> Response:
        project = get_project(self.require(*READ), project_id)
        path = request.query_params.get("path", "")
        if not path:
            raise ValidationFailedError(
                "path is required", [{"field": "path", "message": "required"}]
            )
        ref = request.query_params.get("ref") or "HEAD"
        return _cached(Response(code.read(project, path, ref)), ref)


class CodeLogView(ApiView):
    def get(self, request: Request, project_id: uuid.UUID) -> Response:
        project = get_project(self.require(*READ), project_id)
        raw = request.query_params.get("limit", "50")
        if not raw.isdigit() or not 1 <= int(raw) <= MAX_LOG:
            raise ValidationFailedError(
                f"limit must be 1-{MAX_LOG}", [{"field": "limit", "message": "integer"}]
            )
        ref = request.query_params.get("ref") or "HEAD"
        return Response(code.log(project, ref, int(raw)))


class CodeLocationView(ApiView):
    def get(self, request: Request, project_id: uuid.UUID) -> Response:
        project = get_project(self.require(*READ), project_id)
        return Response(code.location(project))
