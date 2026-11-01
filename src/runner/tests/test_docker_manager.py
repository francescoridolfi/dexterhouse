# SPDX-License-Identifier: AGPL-3.0-or-later
"""DockerManager against a mocked Docker client: the hardening flags and names."""

import uuid
from unittest import mock

import pytest
from docker.errors import APIError, ImageNotFound, NotFound

from dexterhouse_runner.config import RunnerSettings
from dexterhouse_runner.docker_manager import DockerManager, RunnerError, image_ref, quota
from dexterhouse_schema.runner import Limits

SETTINGS = RunnerSettings(
    DH_IMAGE_PREFIX="ghcr.io/acme", RUNNER_ID="r1", PROXY_CONTAINER="dh-proxy"
)


@pytest.mark.parametrize(
    ("image", "expected"),
    [
        ("dexterhouse/workspace:python", "ghcr.io/acme/dexterhouse-workspace:python"),
        ("ghcr.io/acme/dexterhouse-workspace:node", "ghcr.io/acme/dexterhouse-workspace:node"),
        (
            "ghcr.io/acme/dexterhouse-workspace@sha256:" + "1" * 64,
            "ghcr.io/acme/dexterhouse-workspace@sha256:" + "1" * 64,
        ),
    ],
)
def test_image_ref_allowed(image: str, expected: str):
    assert image_ref(image, SETTINGS) == expected


@pytest.mark.parametrize(
    "image", ["docker.io/evil/image", "ghcr.io/acme/dexterhouse-workspace-evil:x", "", "ubuntu"]
)
def test_image_ref_refused(image: str):
    with pytest.raises(RunnerError) as exc:
        image_ref(image, SETTINGS)
    assert exc.value.code == "workspace_not_ready"


def test_quota():
    assert quota(Limits(disk="1G")) == str(1024**3)


def manager() -> tuple[DockerManager, mock.MagicMock]:
    client = mock.MagicMock()
    client.images.get.return_value.id = "sha256:" + "f" * 64
    client.networks.list.return_value = []
    client.networks.create.return_value.name = "dh_sandbox_x"
    client.volumes.create.return_value.name = "dh-ws-x"
    return DockerManager(SETTINGS, client=client), client


def test_create_is_hardened():
    docker, client = manager()
    ws, project = uuid.uuid4(), uuid.uuid4()
    created = docker.create(
        ws, project, "ghcr.io/acme/dexterhouse-workspace:python", {"A": "1"}, [], Limits()
    )
    assert created.digest == "sha256:" + "f" * 64
    network = client.networks.create.call_args
    assert network[0][0] == f"dh_sandbox_{ws}"
    assert network[1]["internal"] is True
    client.networks.create.return_value.connect.assert_called_once_with(
        client.containers.get.return_value, aliases=["proxy"]
    )
    kwargs = client.containers.run.call_args[1]
    assert client.containers.run.call_args[0][0] == created.digest  # by digest, never the tag
    assert kwargs["user"] == "1000:1000"
    assert kwargs["cap_drop"] == ["ALL"]
    assert kwargs["security_opt"] == ["no-new-privileges:true"]
    assert kwargs["read_only"] is True
    assert kwargs["pids_limit"] == 256
    assert kwargs["nano_cpus"] == 2_000_000_000
    assert kwargs["mem_limit"] == "2g"
    assert kwargs["network"] == "dh_sandbox_x"
    assert kwargs["environment"]["HTTPS_PROXY"] == "http://proxy:3128"
    assert kwargs["environment"]["A"] == "1"
    assert "privileged" not in kwargs
    assert not any("docker.sock" in str(v) for v in kwargs["volumes"])
    assert kwargs["labels"]["dexterhouse.workspace"] == str(ws)
    assert kwargs["labels"]["dexterhouse.owner"] == "r1"


def test_sidecar_postgres_exports_a_generated_url():
    docker, client = manager()
    ws = uuid.uuid4()
    docker.create(
        ws,
        uuid.uuid4(),
        "ghcr.io/acme/dexterhouse-workspace:python",
        {},
        ["postgres", "redis"],
        Limits(),
    )
    env = client.containers.run.call_args_list[-1][1]["environment"]
    assert env["DATABASE_URL"].startswith("postgres://app:")
    assert env["DATABASE_URL"].endswith("@postgres:5432/app")
    assert env["REDIS_URL"] == "redis://redis:6379/0"
    names = [c[1]["name"] for c in client.containers.run.call_args_list]
    assert names[:2] == [f"dh-ws-{ws}-postgres", f"dh-ws-{ws}-redis"]
    with pytest.raises(RunnerError):
        docker._sidecar(ws, uuid.uuid4(), "mysql", "net")
    assert docker.services_spec(["redis"]) == [{"name": "redis", "host": "redis", "port": 6379}]


def test_resolve_image_pulls_or_refuses():
    docker, client = manager()
    client.images.get.side_effect = ImageNotFound("x")
    client.images.pull.return_value.id = "sha256:pulled"
    assert docker.resolve_image("ghcr.io/acme/dexterhouse-workspace:python") == "sha256:pulled"
    client.images.pull.side_effect = APIError("denied")
    with pytest.raises(RunnerError):
        docker.resolve_image("ghcr.io/acme/dexterhouse-workspace:python")
    offline = DockerManager(RunnerSettings(WORKSPACE_PULL=False), client=client)
    with pytest.raises(RunnerError):
        offline.resolve_image("x")


def test_destroy_find_managed_exec_archive():
    docker, client = manager()
    container = mock.MagicMock(status="running", labels={"dexterhouse.workspace": "w1"})
    client.containers.list.return_value = [container]
    network = mock.MagicMock(attrs={"Containers": {"abc": {}}})
    client.networks.list.return_value = [network]
    docker.destroy("w1")
    container.remove.assert_called_once_with(force=True, v=True)
    network.disconnect.assert_called_once_with("abc", force=True)
    network.remove.assert_called_once()
    client.volumes.get.return_value.remove.assert_called_once()
    assert docker.managed() == {"w1": "running"}
    client.containers.get.return_value = container
    container.exec_run.return_value = mock.Mock(exit_code=0, output=(b"out", None))
    assert docker.exec("w1", ["true"]) == (0, "out", "")
    container.get_archive.return_value = (iter([b"tar"]), {})
    assert list(docker.archive("w1", "/workspace/.git")) == [b"tar"]
    client.containers.get.side_effect = NotFound("gone")
    assert docker.find("w1") is None
    with pytest.raises(RunnerError):
        docker.running("w1")
    assert docker.proxy() is None


def test_proxy_by_compose_label():
    client = mock.MagicMock()
    client.containers.list.return_value = ["proxy-container"]
    client.containers.get.return_value.labels = {"com.docker.compose.project": "dexterhouse"}
    docker = DockerManager(RunnerSettings(), client=client)
    assert docker.proxy() == "proxy-container"
    assert client.containers.list.call_args[1]["filters"]["label"] == [
        "com.docker.compose.service=proxy",
        "com.docker.compose.project=dexterhouse",
    ]
    network = mock.MagicMock(name="net")
    network.connect.side_effect = APIError("endpoint already exists")
    docker._attach_proxy(network)
    client.containers.list.return_value = []
    docker._attach_proxy(network)  # no proxy: only a warning
