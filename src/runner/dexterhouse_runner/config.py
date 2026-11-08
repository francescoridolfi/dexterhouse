# SPDX-License-Identifier: AGPL-3.0-or-later
"""Runner configuration from the environment (`.env.example`, section Workspaces).

The runner holds no secret but `RUNNER_KEY` (to redeem grants at the core) and never sees
the Fernet key, the database or the providers' keys (ADR-0016, CD-020).
"""

import socket
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

#: Images of the sidecars a stack may declare (`stack.services`), pinned by digest.
SIDECAR_IMAGES = {
    "postgres": "pgvector/pgvector:pg16@sha256:0dd3149a06e4579a0d70d8fef9945636cd514005e7237deb27f9b67886f8dc4f",  # noqa: E501
    "redis": "redis:7.4-alpine@sha256:c5d34a98396a4775e223c74e929162c35c5a2182901ba26b50ade939941ce14b",  # noqa: E501
    "mailpit": "axllent/mailpit:v1.27@sha256:e22dce5b36f93c77082e204a3942fb6b283b7896e057458400a4c88344c3df68",  # noqa: E501
}


class RunnerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=True)

    REDIS_URL: str = "redis://localhost:6379/0"
    RUNNER_ID: str = socket.gethostname()
    RUNNER_KEY: str = ""
    RUNNER_KEY_FILE: str = ""
    CORE_URL: str = "http://web:8000"
    RUNNER_CONCURRENCY: int = 8
    RUNNER_HEARTBEAT_S: float = 15.0
    RUNNER_METRICS_PORT: int = 9100
    # Images: `stack.workspace_image` `dexterhouse/workspace:<flavour>` is mapped under the prefix.
    DH_IMAGE_PREFIX: str = "ghcr.io/francescoridolfi"
    WORKSPACE_IMAGE_ALLOWLIST: str = ""
    WORKSPACE_PULL: bool = True
    RUNNER_RUNTIME: str = "runc"
    WORKSPACE_CPUS: float = 2.0
    WORKSPACE_MEM: str = "2g"
    WORKSPACE_DISK: str = "5G"
    WORKSPACE_PIDS: int = 256
    WORKSPACE_PREFIX: str = "dh-ws"
    # Installation the workspaces belong to (label `dexterhouse.installation`): two stacks on one
    # Docker daemon must not reconcile each other's workspaces. Empty: the runner's compose
    # project, else "default".
    RUNNER_INSTALLATION: str = ""
    # Egress: the proxy container is attached to every sandbox network as `proxy`.
    PROXY_CONTAINER: str = ""
    PROXY_PORT: int = 3128
    DOCKER_CLI: str = "docker"
    WORKSPACE_MCP_COMMAND: str = "dexterhouse-workspace-mcp"
    DELIVERY_TIMEOUT_S: int = 150

    def runner_key(self) -> str:
        if self.RUNNER_KEY:
            return self.RUNNER_KEY
        path = Path(self.RUNNER_KEY_FILE) if self.RUNNER_KEY_FILE else None
        return path.read_text(encoding="utf-8").strip() if path and path.is_file() else ""

    def image_allowlist(self) -> list[str]:
        listed = [i.strip() for i in self.WORKSPACE_IMAGE_ALLOWLIST.split(",") if i.strip()]
        return listed or [f"{self.DH_IMAGE_PREFIX}/dexterhouse-workspace"]


@lru_cache(maxsize=1)
def get_settings() -> RunnerSettings:
    return RunnerSettings()
