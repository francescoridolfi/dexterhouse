# SPDX-License-Identifier: AGPL-3.0-or-later
"""Runner protocol messages of ADR-0018: snapshot, snapshot_drop and restore."""

import uuid

import pytest
from pydantic import ValidationError

from dexterhouse_schema.runner import (
    RUNNER_TASKS,
    Restore,
    Snapshot,
    SnapshotDrop,
    WorkspaceChanged,
    WorkspaceCreate,
)


def test_snapshot_messages_are_registered() -> None:
    assert RUNNER_TASKS["runner.system.snapshot"] is Snapshot
    assert RUNNER_TASKS["runner.system.snapshot_drop"] is SnapshotDrop


def test_snapshot_round_trip() -> None:
    ws, project = uuid.uuid4(), uuid.uuid4()
    dumped = Snapshot(workspace_id=ws, project_id=project).dump()
    assert dumped == {"schema": 1, "workspace_id": str(ws), "project_id": str(project)}
    assert Snapshot.model_validate(dumped).project_id == project
    assert SnapshotDrop.model_validate({"project_id": str(project)}).project_id == project


def test_workspace_create_restore_is_optional() -> None:
    base = {"project_id": str(uuid.uuid4()), "workspace_id": str(uuid.uuid4()), "stack": {}}
    assert WorkspaceCreate.model_validate(base).restore is None
    restored = WorkspaceCreate.model_validate({**base, "restore": {"source": "snapshot"}})
    assert restored.restore == Restore(source="snapshot")
    assert restored.restore.branch == "main"
    assert restored.dump()["restore"]["source"] == "snapshot"


def test_restore_remote_carries_a_grant_not_a_token() -> None:
    grant = uuid.uuid4()
    restore = Restore(
        source="remote", remote_url="https://github.com/o/r.git", token_ref=grant, branch="dev"
    )
    assert restore.dump()["token_ref"] == str(grant)
    with pytest.raises(ValidationError):
        Restore.model_validate({"source": "remote", "token": "ghp_x"})


@pytest.mark.parametrize(
    "payload",
    [{"source": "disk"}, {"source": "remote", "branch": "-x"}, {"source": "remote", "branch": ""}],
)
def test_restore_rejects_bad_values(payload: dict) -> None:
    with pytest.raises(ValidationError):
        Restore.model_validate(payload)


def test_workspace_changed_restored_commit() -> None:
    ws = uuid.uuid4()
    assert WorkspaceChanged(workspace_id=ws, status="ready").restored_commit is None
    changed = WorkspaceChanged(workspace_id=ws, status="ready", restored_commit="a" * 40)
    assert changed.dump()["restored_commit"] == "a" * 40
