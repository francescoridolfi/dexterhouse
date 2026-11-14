# SPDX-License-Identifier: AGPL-3.0-or-later
"""workspace.*, branch.*, commit.*, test.*, secrets.*, release.* payloads.

See contracts/events/workspace_release.md.
"""

import uuid
from typing import Literal

from dexterhouse.apps.events.schemas.base import EventPayload
from dexterhouse.apps.events.schemas.common import _Strict

DeliveryMode = Literal["push_main", "pull_request"]
TestScope = Literal["task", "integration", "smoke"]

# workspace.*


class Stack(_Strict):
    language: str
    framework: str
    workspace_image: str


class WorkspaceRequested(EventPayload):
    event_type = "workspace.requested"

    project_id: uuid.UUID
    stack: Stack


class WorkspaceCreated(EventPayload):
    event_type = "workspace.created"

    workspace_id: uuid.UUID
    image: str
    digest: str
    services: list[str]


class WorkspaceError(EventPayload):
    event_type = "workspace.error"

    attempt: int
    error_detail: str


class WorkspaceIdle(EventPayload):
    event_type = "workspace.idle"


class WorkspaceResumed(EventPayload):
    event_type = "workspace.resumed"


class WorkspaceDestroyed(EventPayload):
    event_type = "workspace.destroyed"

    reason: Literal["completed", "archived", "inactive"]


# branch.*, commit.*


class BranchCreated(EventPayload):
    event_type = "branch.created"

    task_id: uuid.UUID
    branch: str


class BranchMerged(EventPayload):
    event_type = "branch.merged"

    task_id: uuid.UUID
    branch: str
    commit: str
    files_changed: int
    insertions: int
    deletions: int


class CommitCreated(EventPayload):
    event_type = "commit.created"
    actors = ("agent",)

    task_id: uuid.UUID
    branch: str
    commit: str
    message: str
    files_changed: int


# test.*  (the agent runs them, and the core re-runs integration tests as `system`)


class TestRunStarted(EventPayload):
    event_type = "test.run.started"
    actors = ("agent", "system")

    task_id: uuid.UUID | None = None
    scope: TestScope
    command: str


class ReportRef(_Strict):
    id: uuid.UUID
    version: int


class TestRunCompleted(EventPayload):
    event_type = "test.run.completed"
    actors = ("agent", "system")

    task_id: uuid.UUID | None = None
    scope: TestScope
    passed: int
    failed: int
    skipped: int
    duration_s: float
    ok: bool
    report_artifact: ReportRef


# secrets.*


class SecretsBlocked(EventPayload):
    event_type = "secrets.blocked"

    task_id: uuid.UUID
    files: list[str]
    count: int


# release.*


class TestTotals(_Strict):
    passed: int
    failed: int


class ReleasePrepared(EventPayload):
    event_type = "release.prepared"
    actors = ("agent",)

    release_notes_artifact: uuid.UUID
    commits: int
    tests: TestTotals


class ReleaseDelivered(EventPayload):
    event_type = "release.delivered"

    mode: DeliveryMode
    remote_url: str
    commit: str
    pr_url: str | None = None
    branch: str | None = None


class ReleaseFailed(EventPayload):
    event_type = "release.failed"

    mode: DeliveryMode
    error_code: Literal["auth", "protected_branch", "conflict", "network"]
    detail: str
