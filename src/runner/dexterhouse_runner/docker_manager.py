# SPDX-License-Identifier: AGPL-3.0-or-later
"""Docker resources of a workspace: network, volume, sidecars and the hardened container.

Names (state_machines/workspace.md, infra/workspace_images.md, CD-022): container and volume
`<prefix>-<id>`, sidecars `<prefix>-<id>-<service>`, network `dh_sandbox_<id>` (internal: no
route out, only the proxy is attached to it as `proxy`). Every resource carries the labels
`dexterhouse.workspace`, `dexterhouse.project`, `dexterhouse.owner`, `dexterhouse.role` so
the runner can reconcile after a restart and the tests can clean up by label, and
`dexterhouse.installation`, so it only reconciles the workspaces of its own stack.
"""

import secrets
import socket
import uuid
from dataclasses import dataclass, field
from typing import Any

import docker
import structlog
from docker.errors import APIError, ImageNotFound, NotFound

from dexterhouse_runner.config import SIDECAR_IMAGES, RunnerSettings
from dexterhouse_runner.workspace_mcp.base import parse_size

logger = structlog.get_logger(__name__)

WORKDIR = "/workspace"
USER = "1000:1000"
LABEL = "dexterhouse.workspace"
SHORT_IMAGES = {f"dexterhouse/workspace:{f}": f for f in ("python", "node", "full")}
_SIDECAR_PORTS = {"postgres": 5432, "redis": 6379, "mailpit": 1025}


class RunnerError(Exception):
    """A failure with a protocol error code (`dexterhouse_schema.runner.ErrorCode`)."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass
class Created:
    container_id: str
    image: str
    digest: str
    services: list[str] = field(default_factory=list)


def image_ref(stack_image: str, settings: RunnerSettings) -> str:
    """`dexterhouse/workspace:python` -> `<prefix>/dexterhouse-workspace:python` (allowlisted)."""
    image = (stack_image or "").strip()
    if image in SHORT_IMAGES:
        image = f"{settings.DH_IMAGE_PREFIX}/dexterhouse-workspace:{SHORT_IMAGES[image]}"
    head, _, last = image.split("@", 1)[0].rpartition("/")
    repository = f"{head}/{last.split(':')[0]}" if head else last.split(":")[0]
    if not image or repository not in settings.image_allowlist():
        raise RunnerError(
            "workspace_not_ready",
            f"image {stack_image!r} is not allowed (WORKSPACE_IMAGE_ALLOWLIST)",
        )
    return image


class DockerManager:
    def __init__(self, settings: RunnerSettings, client: Any = None) -> None:
        self.settings = settings
        self.client = client or docker.from_env(timeout=120)

    # Names --------------------------------------------------------------------------------

    def name(self, workspace_id: uuid.UUID | str) -> str:
        return f"{self.settings.WORKSPACE_PREFIX}-{workspace_id}"

    @staticmethod
    def network_name(workspace_id: uuid.UUID | str) -> str:
        return f"dh_sandbox_{workspace_id}"

    def labels(self, workspace_id: Any, project_id: Any, role: str) -> dict[str, str]:
        return {
            LABEL: str(workspace_id),
            "dexterhouse.project": str(project_id),
            "dexterhouse.owner": self.settings.RUNNER_ID,
            "dexterhouse.role": role,
            "dexterhouse.prefix": self.settings.WORKSPACE_PREFIX,
            "dexterhouse.installation": self.installation(),
        }

    def installation(self) -> str:
        """RUNNER_INSTALLATION, else this runner's compose project, else `default`."""
        return self.settings.RUNNER_INSTALLATION or self._compose_project() or "default"

    # Images -------------------------------------------------------------------------------

    def resolve_image(self, ref: str) -> str:
        """The local image id (`sha256:…`) of `ref`, pulled by tag or digest when missing."""
        try:
            return self.client.images.get(ref).id
        except ImageNotFound:
            if not self.settings.WORKSPACE_PULL:
                raise RunnerError("workspace_not_ready", f"image {ref} is not present") from None
        try:
            return self.client.images.pull(ref).id
        except (APIError, ImageNotFound) as exc:
            raise RunnerError("workspace_not_ready", f"cannot pull {ref}: {exc}") from exc

    # Lifecycle ----------------------------------------------------------------------------

    def find(self, workspace_id: Any) -> Any | None:
        try:
            return self.client.containers.get(self.name(workspace_id))
        except NotFound:
            return None

    def create(
        self,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        image: str,
        env: dict[str, str],
        services: list[str],
        limits: Any,
    ) -> Created:
        digest = self.resolve_image(image)
        network = self._network(workspace_id, project_id)
        self._attach_proxy(network)
        volume = self.client.volumes.create(
            name=self.name(workspace_id), labels=self.labels(workspace_id, project_id, "volume")
        )
        service_env: dict[str, str] = {}
        for service in services:
            service_env |= self._sidecar(workspace_id, project_id, service, network.name)
        proxy = f"http://proxy:{self.settings.PROXY_PORT}"
        environment = {
            "HTTP_PROXY": proxy,
            "HTTPS_PROXY": proxy,
            "http_proxy": proxy,
            "https_proxy": proxy,
            "NO_PROXY": "localhost,127.0.0.1",
            "no_proxy": "localhost,127.0.0.1",
            "HOME": "/home/dh",
            "CI": "1",
            **service_env,
            **env,
        }
        container = self.client.containers.run(
            digest,
            name=self.name(workspace_id),
            hostname="workspace",
            detach=True,
            user=USER,
            working_dir=WORKDIR,
            environment=environment,
            labels=self.labels(workspace_id, project_id, "workspace")
            | {"dexterhouse.image": image},
            network=network.name,
            volumes={volume.name: {"bind": WORKDIR, "mode": "rw"}},
            read_only=True,
            tmpfs={"/tmp": "size=512m,mode=1777", "/home/dh": "size=512m,uid=1000,gid=1000"},  # noqa: S108  # nosec B108
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            pids_limit=limits.pids,
            nano_cpus=int(limits.cpus * 1e9),
            mem_limit=limits.memory,
            memswap_limit=limits.memory,
            init=True,
            runtime=self.settings.RUNNER_RUNTIME,
            auto_remove=False,
        )
        return Created(container.id, image, digest, services)

    def _network(self, workspace_id: Any, project_id: Any) -> Any:
        name = self.network_name(workspace_id)
        existing = self.client.networks.list(names=[name])
        if existing:
            return existing[0]
        return self.client.networks.create(
            name,
            driver="bridge",
            internal=True,
            labels=self.labels(workspace_id, project_id, "network"),
        )

    def proxy(self) -> Any | None:
        """The `proxy` service container (PROXY_CONTAINER, else the compose service label)."""
        if self.settings.PROXY_CONTAINER:
            try:
                return self.client.containers.get(self.settings.PROXY_CONTAINER)
            except NotFound:
                return None
        labels = ["com.docker.compose.service=proxy"]
        project = self._compose_project()
        if project:  # the proxy of this runner's own compose project, not another stack's
            labels.append(f"com.docker.compose.project={project}")
        found = self.client.containers.list(filters={"label": labels})
        return found[0] if found else None

    def _compose_project(self) -> str | None:
        if not hasattr(self, "_project"):
            try:
                own = self.client.containers.get(socket.gethostname())
                self._project = (own.labels or {}).get("com.docker.compose.project")
            except (NotFound, APIError):
                self._project = None
        return self._project

    def _attach_proxy(self, network: Any) -> None:
        proxy = self.proxy()
        if proxy is None:
            logger.warning("runner.proxy_missing", network=network.name)
            return
        try:
            network.connect(proxy, aliases=["proxy"])
        except APIError as exc:
            if "already exists" not in str(exc):
                raise

    def _sidecar(
        self, workspace_id: Any, project_id: Any, service: str, network: str
    ) -> dict[str, str]:
        """Start one `stack.services` sidecar; returns the variables the workspace gets."""
        image = SIDECAR_IMAGES.get(service)
        if image is None:
            raise RunnerError("workspace_not_ready", f"unknown service {service!r}")
        name = f"{self.name(workspace_id)}-{service}"
        password = secrets.token_urlsafe(18)
        environment: dict[str, str] = {}
        exported: dict[str, str] = {}
        tmpfs: dict[str, str] = {}
        if service == "postgres":
            environment = {
                "POSTGRES_USER": "app",
                "POSTGRES_PASSWORD": password,
                "POSTGRES_DB": "app",
            }
            exported = {"DATABASE_URL": f"postgres://app:{password}@{service}:5432/app"}
            tmpfs = {"/var/lib/postgresql/data": "size=256m"}
        elif service == "redis":
            exported = {"REDIS_URL": f"redis://{service}:6379/0"}
        else:
            exported = {"SMTP_HOST": service, "SMTP_PORT": "1025"}
        self.client.containers.run(
            self.resolve_image(image),
            name=name,
            detach=True,
            environment=environment,
            labels=self.labels(workspace_id, project_id, "sidecar")
            | {"dexterhouse.service": service},
            network=network,
            tmpfs=tmpfs or None,
            cap_drop=["ALL"],
            cap_add=["CHOWN", "SETUID", "SETGID", "DAC_OVERRIDE", "FOWNER"],
            security_opt=["no-new-privileges:true"],
            pids_limit=256,
            mem_limit="512m",
            runtime=self.settings.RUNNER_RUNTIME,
        )
        network_obj = self.client.networks.get(network)
        network_obj.disconnect(name)
        network_obj.connect(name, aliases=[service])
        return exported

    def services_spec(self, services: list[str]) -> list[dict[str, Any]]:
        return [{"name": s, "host": s, "port": _SIDECAR_PORTS[s]} for s in services]

    def destroy(self, workspace_id: Any) -> None:
        """Remove containers, network and volume of the workspace (idempotent)."""
        for container in self.client.containers.list(
            all=True, filters={"label": f"{LABEL}={workspace_id}"}
        ):
            try:
                container.remove(force=True, v=True)
            except NotFound:
                pass
        for network in self.client.networks.list(names=[self.network_name(workspace_id)]):
            network.reload()
            for attached in network.attrs.get("Containers", {}) or {}:
                try:
                    network.disconnect(attached, force=True)
                except (APIError, NotFound):
                    pass
            try:
                network.remove()
            except NotFound:
                pass
        try:
            self.client.volumes.get(self.name(workspace_id)).remove(force=True)
        except NotFound:
            pass

    def managed(self) -> dict[str, str]:
        """Workspaces of this installation and prefix: {workspace_id: container status}."""
        found = self.client.containers.list(
            all=True,
            filters={
                "label": [
                    "dexterhouse.role=workspace",
                    f"dexterhouse.prefix={self.settings.WORKSPACE_PREFIX}",
                    f"dexterhouse.installation={self.installation()}",
                ]
            },
        )
        return {c.labels[LABEL]: c.status for c in found}

    def running(self, workspace_id: Any) -> Any:
        container = self.find(workspace_id)
        if container is None or container.status != "running":
            raise RunnerError("workspace_not_ready", "the workspace container is not running")
        return container

    def exec(
        self,
        workspace_id: Any,
        argv: list[str],
        env: dict[str, str] | None = None,
        workdir: str = WORKDIR,
    ) -> tuple[int, str, str]:
        container = self.running(workspace_id)
        result = container.exec_run(
            argv, user=USER, workdir=workdir, environment=env or {}, demux=True
        )
        out, err = result.output if result.output else (b"", b"")
        return (
            result.exit_code,
            (out or b"").decode("utf-8", errors="replace"),
            (err or b"").decode("utf-8", errors="replace"),
        )

    def archive(self, workspace_id: Any, path: str) -> Any:
        """A tar stream of `path` in the workspace (the repository for `deliver`)."""
        stream, _stat = self.running(workspace_id).get_archive(path)
        return stream


def quota(limits: Any) -> str:
    return str(parse_size(limits.disk))
