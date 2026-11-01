# SPDX-License-Identifier: AGPL-3.0-or-later
import json
import urllib.error
import uuid
from pathlib import Path
from unittest import mock

import pytest

from dexterhouse_runner import tasks
from dexterhouse_runner.callbacks import Callbacks
from dexterhouse_runner.config import RunnerSettings
from dexterhouse_runner.docker_manager import RunnerError
from dexterhouse_runner.grants import redeem
from dexterhouse_schema.runner import Heartbeat, ToolResult


class _Response:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.body


def test_redeem_sends_the_runner_key(tmp_path: Path):
    key = tmp_path / "runner_key"
    key.write_text("abc\n")
    settings = RunnerSettings(CORE_URL="http://web:8000/", RUNNER_KEY_FILE=str(key))
    grant = uuid.uuid4()
    with mock.patch("urllib.request.urlopen", return_value=_Response(b'{"value": "tok"}')) as call:
        assert redeem(grant, settings) == "tok"
    request = call.call_args[0][0]
    assert request.full_url == f"http://web:8000/internal/secrets/{grant}"
    assert request.headers["X-runner-key"] == "abc"


@pytest.mark.parametrize(
    ("effect", "code"),
    [
        (urllib.error.HTTPError("u", 404, "gone", {}, None), "auth"),
        (urllib.error.URLError("down"), "network"),
        (_Response(b'{"value": ""}'), "auth"),
    ],
)
def test_redeem_failures(effect, code: str):
    settings = RunnerSettings(RUNNER_KEY="k")
    patch = {"side_effect": effect} if isinstance(effect, Exception) else {"return_value": effect}
    with mock.patch("urllib.request.urlopen", **patch), pytest.raises(RunnerError) as exc:
        redeem(uuid.uuid4(), settings)
    assert exc.value.code == code


def test_redeem_needs_a_key_and_http():
    with pytest.raises(RunnerError):
        redeem(uuid.uuid4(), RunnerSettings(RUNNER_KEY=""))
    with pytest.raises(RunnerError):
        redeem(uuid.uuid4(), RunnerSettings(RUNNER_KEY="k", CORE_URL="file:///etc"))


def test_settings_allowlist():
    assert RunnerSettings(DH_IMAGE_PREFIX="ghcr.io/x").image_allowlist() == [
        "ghcr.io/x/dexterhouse-workspace"
    ]
    assert RunnerSettings(WORKSPACE_IMAGE_ALLOWLIST="a/b, c/d").image_allowlist() == ["a/b", "c/d"]


def test_tasks_validate_and_dispatch():
    fake = mock.Mock()
    fake.status.return_value = ToolResult(ok=True, data={"status": "ready"})
    with mock.patch.object(tasks, "service", return_value=fake):
        ws = str(uuid.uuid4())
        result = tasks.app.tasks["runner.workspace.status"].run({"schema": 1, "workspace_id": ws})
        assert result["ok"] is True
        bad = tasks.app.tasks["runner.workspace.status"].run({"schema": 2, "workspace_id": ws})
    assert bad["error"]["code"] == "internal"
    assert set(tasks.app.tasks) >= {
        "runner.tool.invoke",
        "runner.system.deliver",
        "runner.tool.list",
    }
    assert tasks.app.tasks["runner.tool.invoke"].queue == "runner"


def test_heartbeat_loop_stops():
    fake = mock.Mock()
    fake.heartbeat.side_effect = [RuntimeError("docker down"), None]
    with (
        mock.patch.object(tasks, "service", return_value=fake),
        mock.patch.object(tasks, "_stop") as stop,
    ):
        stop.wait.side_effect = [False, True]
        tasks._heartbeat_loop()
    assert fake.heartbeat.call_count == 2


def test_callbacks_go_to_the_core_queue():
    app = mock.Mock()
    callbacks = Callbacks(app)
    callbacks.heartbeat(Heartbeat(runner_id="r", version="1", active_workspaces=0))
    name = app.send_task.call_args[0][0]
    assert name == "core.runner.heartbeat"
    assert app.send_task.call_args[1]["queue"] == "core-callbacks"
    assert json.dumps(app.send_task.call_args[1]["args"][0])
    app.send_task.side_effect = OSError("broker down")
    callbacks.heartbeat(Heartbeat(runner_id="r", version="1", active_workspaces=0))  # logged only
