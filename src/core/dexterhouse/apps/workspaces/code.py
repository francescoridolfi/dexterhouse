# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only access to the code the agents wrote, for the UI's Code app (docs/api.md).

Every read goes through the runner client with a system task (`runner.system.ls_tree`,
`read_file`, `commit_log`): no agent turn, no tool call, no checkout, and the workspace's
inactivity clock is not reset. "Where is the code" combines the workspace row, the latest
commit and the `release.delivered` events (branch and pull request of each release).
"""

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import ValidationError

from dexterhouse.apps.events.models import Event
from dexterhouse.apps.projects.models import Project
from dexterhouse.apps.workspaces import services
from dexterhouse.apps.workspaces.client import get_client
from dexterhouse.apps.workspaces.models import Workspace
from dexterhouse.common.errors import DomainError, ValidationFailedError
from dexterhouse_schema.runner import CommitLog, LsTree, Message, ReadFile, ToolResult

#: Where the repository lives inside every workspace container (the runner's WORKDIR).
WORKSPACE_PATH = "/workspace"
UNAVAILABLE = ("workspace_not_ready", "timeout", "internal")


class CodeUnavailableError(DomainError):
    """No live workspace, or the runner did not answer: the code cannot be read now."""

    status = 503
    slug = "workspace-unavailable"
    title = "Workspace unavailable"


class CodeNotFoundError(DomainError):
    status = 404
    slug = "not-found"
    title = "Not found"


def _workspace(project: Project) -> Workspace:
    workspace = services.live(project.id)
    if workspace is None:
        raise CodeUnavailableError("the project has no live workspace")
    return workspace


def _call(task: str, message: Message) -> dict[str, Any]:
    result: ToolResult = get_client().call(task, message)
    if result.ok:
        return dict(result.data or {})
    code = result.error.code if result.error else "internal"
    detail = result.error.detail if result.error else task
    if code == "not_found":
        raise CodeNotFoundError(detail)
    if code == "invalid":
        raise ValidationFailedError(detail, [{"field": "path", "message": detail}])
    raise CodeUnavailableError(detail)


def _validated(model: type[Message], **fields: Any) -> Message:
    try:
        return model(**fields)
    except ValidationError as exc:
        errors = [
            {"field": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in exc.errors()
        ]
        raise ValidationFailedError("invalid parameters", errors) from exc


def tree(project: Project, ref: str) -> dict[str, Any]:
    workspace = _workspace(project)
    return _call("runner.system.ls_tree", _validated(LsTree, workspace_id=workspace.id, ref=ref))


def read(project: Project, path: str, ref: str) -> dict[str, Any]:
    workspace = _workspace(project)
    message = _validated(ReadFile, workspace_id=workspace.id, path=path, ref=ref)
    return _call("runner.system.read_file", message)


def log(project: Project, ref: str, limit: int) -> dict[str, Any]:
    workspace = _workspace(project)
    message = _validated(CommitLog, workspace_id=workspace.id, ref=ref, max=limit)
    data = _call("runner.system.commit_log", message)
    return {"ref": ref, "branch": data.get("branch"), "commits": data.get("commits", [])}


def public_url(url: str | None) -> str | None:
    """The remote URL without the user and password part, if any."""
    if not url:
        return None
    parts = urlsplit(url)
    if not parts.scheme or not parts.hostname:
        return url
    host = parts.hostname + (f":{parts.port}" if parts.port else "")
    return urlunsplit((parts.scheme, host, parts.path, parts.query, ""))


def web_url(remote: str | None) -> str | None:
    """Browsable URL of an https GitHub/GitLab-style remote (no `.git`), else None."""
    if not remote or not remote.startswith("https://"):
        return None
    return remote.removesuffix("/").removesuffix(".git")


def releases(project: Project) -> list[dict[str, Any]]:
    rows = Event.objects.filter(project_id=project.id, type="release.delivered").order_by(
        "created_at", "id"
    )
    out = []
    for number, event in enumerate(rows, start=1):
        payload = event.payload or {}
        mode = payload.get("mode")
        branch = payload.get("branch") or (
            f"dexterhouse/release-{number}" if mode == "pull_request" else "main"
        )
        out.append(
            {
                "number": number,
                "mode": mode,
                "branch": branch,
                "commit": payload.get("commit") or None,
                "pr_url": payload.get("pr_url"),
                "remote_url": public_url(payload.get("remote_url")),
                "delivered_at": event.created_at.isoformat(),
            }
        )
    return out[::-1]


def location(project: Project) -> dict[str, Any]:
    workspace = services.live(project.id)
    head: dict[str, Any] | None = None
    branch: str | None = None
    error: str | None = None
    if workspace is None:
        error = "the project has no live workspace"
    else:
        try:
            data = log(project, "HEAD", 1)
            head = (data["commits"] or [None])[0]
            branch = data["branch"]
        except (CodeUnavailableError, CodeNotFoundError) as exc:
            error = exc.detail
    remote = public_url(project.remote_repo_url)
    return {
        "workspace": None
        if workspace is None
        else {
            "id": str(workspace.id),
            "status": workspace.status,
            "path": WORKSPACE_PATH,
            "volume": workspace.volume or None,
            "container_id": workspace.container_id,
            "image": workspace.image or None,
        },
        "branch": branch,
        "head": head,
        "unavailable": error,
        "remote_url": remote,
        "web_url": web_url(remote),
        "delivery_mode": project.delivery_mode,
        "releases": releases(project),
    }
