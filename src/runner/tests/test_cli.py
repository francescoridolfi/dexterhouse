# SPDX-License-Identifier: AGPL-3.0-or-later
from unittest import mock

import pytest

from dexterhouse_runner import __version__
from dexterhouse_runner.cli import main


def test_version(capsys: pytest.CaptureFixture[str]):
    assert main(["version"]) == 0
    assert capsys.readouterr().out.strip() == __version__


def test_health(capsys: pytest.CaptureFixture[str]):
    with mock.patch("docker.from_env") as docker, mock.patch("redis.Redis.from_url") as redis:
        assert main([]) == 0
        docker.return_value.ping.assert_called_once()
        redis.return_value.ping.assert_called_once()
        assert capsys.readouterr().out.strip() == "ok"
        docker.return_value.ping.side_effect = OSError("no socket")
        assert main(["health"]) == 1
    assert "unhealthy" in capsys.readouterr().err


def test_worker_starts_celery_on_the_runner_queue():
    with mock.patch("dexterhouse_runner.tasks.app.worker_main") as worker_main:
        assert main(["worker", "--loglevel", "debug"]) == 0
    argv = worker_main.call_args[0][0]
    assert argv[:6] == ["worker", "-Q", "runner", "-P", "threads", "-c"]
    assert argv[-2:] == ["--loglevel", "debug"]


def test_unknown_command(capsys: pytest.CaptureFixture[str]):
    assert main(["explode"]) == 2
    assert "unknown command" in capsys.readouterr().err
