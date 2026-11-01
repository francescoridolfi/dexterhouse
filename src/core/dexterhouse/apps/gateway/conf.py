# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gateway configuration from the environment (provider keys are never stored in the repo)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewayEnv(BaseSettings):
    """Variables documented in `.env.example`; keys are read at call time, never persisted."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=True)

    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_BASE_URL: str = ""
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = ""
    OPENAI_COMPATIBLE_BASE_URL: str = ""
    OPENAI_COMPATIBLE_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    CLAUDE_CLI_PATH: str = "claude"
    CLAUDE_CLI_HOME: str = ""
    CLI_MAX_CONCURRENT: int = Field(default=2, ge=1)
    CLI_TIMEOUT_S: int = Field(default=600, ge=1)
    GATEWAY_TIMEOUT_S: float = Field(default=300.0, gt=0)


@lru_cache(maxsize=1)
def get_gateway_env() -> GatewayEnv:
    """Cached environment; tests call `get_gateway_env.cache_clear()` after patching."""
    return GatewayEnv()
