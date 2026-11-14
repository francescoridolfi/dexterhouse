# SPDX-License-Identifier: AGPL-3.0-or-later
"""The `code_graph` artifact and its summary (runner `runner.system.code_graph`).

After every successful `git.commit` of an agent, `schedule_refresh` queues
`refresh_code_graph`, which asks the runner for the whole graph and saves a new version of
`code_graph.json` unless the latest one is already at that commit. `summary` is what the
context builder puts in the workspace tree section at the start of a turn.
"""

import uuid
from typing import Any

import structlog
from django.db import transaction

from dexterhouse.apps.projects.models import Artifact, ArtifactKind, Project
from dexterhouse.apps.projects.services.artifacts import save_artifact
from dexterhouse.common.errors import ValidationFailedError
from dexterhouse_schema.runner import CodeGraph

logger = structlog.get_logger(__name__)

NAME = "code_graph.json"
EXPORT_TIMEOUT_S = 120
#: Characters asked for the summary; the context builder cuts it to the profile's budget.
SUMMARY_CHARS = 7200


def _export(project_id: Any, *, include_graph: bool) -> dict[str, Any] | None:
    from dexterhouse.apps.workspaces.client import get_client
    from dexterhouse.apps.workspaces.services import live

    workspace = live(project_id)
    if workspace is None:
        return None
    message = CodeGraph(
        workspace_id=workspace.id, include_graph=include_graph, summary_chars=SUMMARY_CHARS
    )
    result = get_client().call("runner.system.code_graph", message, timeout_s=EXPORT_TIMEOUT_S)
    if not result.ok or not isinstance(result.data, dict):
        logger.info(
            "workspaces.code_graph_unavailable",
            project_id=str(project_id),
            error=result.error.model_dump() if result.error else None,
        )
        return None
    return result.data


def summary(project_id: Any) -> str | None:
    data = _export(project_id, include_graph=False)
    return str(data["summary"]) if data and data.get("summary") else None


def refresh(project_id: Any, turn_id: uuid.UUID | None = None, role: str = "") -> Artifact | None:
    """Save the workspace's graph as the next `code_graph` version (None: nothing new)."""
    data = _export(project_id, include_graph=True)
    graph = (data or {}).get("graph")
    if not isinstance(graph, dict):
        return None
    latest = (
        Artifact.objects.filter(project_id=project_id, kind=ArtifactKind.CODE_GRAPH, name=NAME)
        .order_by("-version")
        .first()
    )
    commit = graph.get("commit")
    if commit and latest is not None and (latest.data or {}).get("commit") == commit:
        return None  # already saved for this commit
    project = Project.objects.get(pk=project_id)
    try:
        with transaction.atomic():
            return save_artifact(
                project,
                kind=ArtifactKind.CODE_GRAPH,
                name=NAME,
                data=graph,
                turn_id=turn_id,
                role=role,
            )
    except ValidationFailedError as exc:
        logger.warning("workspaces.code_graph_invalid", project_id=str(project_id), error=str(exc))
        return None


def schedule_refresh(project_id: Any, turn_id: uuid.UUID | None, role: str) -> None:
    from dexterhouse.apps.workspaces.tasks import refresh_code_graph

    args = (str(project_id), str(turn_id) if turn_id else None, role)
    transaction.on_commit(lambda: refresh_code_graph.delay(*args), robust=True)
