# SPDX-License-Identifier: AGPL-3.0-or-later
"""Environment configuration read with pydantic-settings; no secret has a default."""

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def read_secret_file(path: str) -> str:
    """Return the stripped content of a secret file, or an empty string if it is missing."""
    if not path:
        return ""
    file = Path(path)
    return file.read_text(encoding="utf-8").strip() if file.is_file() else ""


class Env(BaseSettings):
    """Variables documented in `.env.example`; `*_FILE` variants point to generated secrets."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=True)

    SECRET_KEY: str = ""
    SECRET_KEY_FILE: str = ""
    DEBUG: bool = False
    ALLOWED_HOSTS: str = "localhost"
    CSRF_TRUSTED_ORIGINS: str = "http://localhost"
    DATABASE_URL: str = "postgres://dexterhouse@localhost:5432/dexterhouse"
    DATABASE_PASSWORD_FILE: str = ""
    REDIS_URL: str = "redis://localhost:6379/0"
    DEFAULT_ORG_SLUG: str = "default"
    DEFAULT_LANGUAGE: str = "en"
    TZ: str = "UTC"
    STATIC_ROOT: str = ""
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    EVENTS_RETENTION_MONTHS: int = Field(default=12, ge=1)
    PRICES_FILE: str = ""
    FX_EUR_PER_USD: str = ""
    FERNET_KEY: str = ""
    FERNET_KEY_FILE: str = ""
    BUILTIN_DIR: str = ""
    EMAIL_HOST: str = "localhost"
    EMAIL_PORT: int = 25
    EMAIL_HOST_USER: str = ""
    EMAIL_HOST_PASSWORD_FILE: str = ""
    EMAIL_USE_TLS: bool = False
    DEFAULT_FROM_EMAIL: str = "DexterHouse <noreply@localhost>"
    NOTIFICATIONS_EMAIL: bool = False
    PUBLIC_URL: str = "http://localhost"
    GATEWAY_FAKE_RESPONDER: str = ""
    RUNNER_KEY: str = ""
    RUNNER_KEY_FILE: str = ""
    DH_IMAGE_PREFIX: str = "ghcr.io/francescoridolfi"
    WORKSPACE_CPUS: float = 2.0
    WORKSPACE_MEM: str = "2g"
    WORKSPACE_DISK: str = "5G"
    WORKSPACE_IDLE_DESTROY_H: int = 24
    PACKAGES_DIR: str = "/data/packages"
    REGISTRY_INDEX_URL: str = ""
    MARKETPLACE_URL: str = ""
    PACKAGES_ALLOW_LOCAL: bool = False
    PACKAGES_GIT_MIRRORS: dict[str, str] = Field(default_factory=dict)  # JSON {prefix: mirror}
    MARKETPLACE_RAW_URL: str = ""
    API_RATE_CLIENT: str = "600/min"
    API_RATE_ANON: str = "60/min"
    API_RATE_LOGIN: str = "10/min"
    API_TRUSTED_PROXIES: int = Field(default=1, ge=0)
    WS_CONNECTIONS_PER_PROJECT: int = Field(default=1, ge=1)

    def secret_key(self) -> str:
        """SECRET_KEY from env, else from SECRET_KEY_FILE."""
        return self.SECRET_KEY or read_secret_file(self.SECRET_KEY_FILE)

    def fernet_key(self) -> str:
        """FERNET_KEY from env, else from FERNET_KEY_FILE."""
        return self.FERNET_KEY or read_secret_file(self.FERNET_KEY_FILE)

    def runner_key(self) -> str:
        """RUNNER_KEY from env, else from RUNNER_KEY_FILE (shared with the runner only)."""
        return self.RUNNER_KEY or read_secret_file(self.RUNNER_KEY_FILE)

    def database_url(self) -> str:
        """DATABASE_URL with the password from DATABASE_PASSWORD_FILE when the URL has none."""
        password = read_secret_file(self.DATABASE_PASSWORD_FILE)
        parts = urlsplit(self.DATABASE_URL)
        if not password or parts.password:
            return self.DATABASE_URL
        user = parts.username or ""
        host = parts.hostname or ""
        netloc = f"{user}:{quote(password, safe='')}@{host}"
        if parts.port:
            netloc += f":{parts.port}"
        return urlunsplit(parts._replace(netloc=netloc))

    @staticmethod
    def split(value: str) -> list[str]:
        """Split a comma separated variable."""
        return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_env() -> Env:
    """Cached environment."""
    return Env()
