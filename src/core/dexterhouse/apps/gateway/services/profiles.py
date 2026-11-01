# SPDX-License-Identifier: AGPL-3.0-or-later
"""Resolve a profile (`strong|balanced|fast|embed`) to provider + model (llm_gateway.md).

Lookup order: project override, organization row, installation default. Agents ask for a
profile, never for a model, so packages stay portable across installations.
"""

import os
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from dexterhouse.apps.gateway.models import ModelProfile
from dexterhouse.apps.gateway.providers import LOCAL_PROVIDERS, ProviderConfig, ProviderError

DataResidency = Literal["any", "local"]

#: Installation default when no `ModelProfile` row exists: `anthropic` via API key.
DEFAULT_PROFILES: dict[str, tuple[str, str]] = {
    "strong": ("anthropic", "claude-opus-5-5"),
    "balanced": ("anthropic", "claude-sonnet-5-5"),
    "fast": ("anthropic", "claude-haiku-5-5"),
}
DOWNGRADE: dict[str, str] = {"strong": "balanced", "balanced": "fast"}
DEFAULT_KEY_ENV: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openai-compatible": "OPENAI_COMPATIBLE_API_KEY",
}


class ProfileConfigurationError(ProviderError):
    """The profile cannot serve this call (residency, tool use, opt-in): shown at the gate."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="configuration")


@dataclass(frozen=True)
class ResolvedProfile:
    profile: str
    provider: str
    model: str
    base_url: str = ""
    api_key_env: str = ""
    options: Mapping[str, Any] = field(default_factory=dict)
    is_local: bool = False
    source: Literal["project", "organization", "default"] = "default"

    @property
    def local(self) -> bool:
        """True when no data leaves the installation (`data_residency: local`)."""
        if self.provider in LOCAL_PROVIDERS:
            return True
        return self.provider == "openai-compatible" and self.is_local

    @property
    def supports_tools(self) -> bool:
        return bool(self.options.get("tools", True))

    def config(self, http_client: Any = None) -> ProviderConfig:
        env_name = self.api_key_env or DEFAULT_KEY_ENV.get(self.provider, "")
        return ProviderConfig(
            api_key=os.environ.get(env_name, "") if env_name else "",
            base_url=self.base_url,
            options={**self.options, "is_local": self.is_local},
            http_client=http_client,
        )


def resolve_profile(
    organization_id: uuid.UUID, project_id: uuid.UUID | None, profile: str
) -> ResolvedProfile:
    rows = ModelProfile.objects.filter(organization_id=organization_id, profile=profile)
    row = rows.filter(project_id=project_id).first() if project_id else None
    source: Literal["project", "organization", "default"] = "project"
    if row is None:
        row = rows.filter(project_id__isnull=True).first()
        source = "organization"
    if row is not None:
        return ResolvedProfile(
            profile=profile,
            provider=row.provider,
            model=row.model,
            base_url=row.base_url,
            api_key_env=row.api_key_env,
            options=dict(row.options),
            is_local=row.is_local,
            source=source,
        )
    if profile not in DEFAULT_PROFILES:
        raise ProfileConfigurationError(f"profile {profile!r} is not configured")
    provider, model = DEFAULT_PROFILES[profile]
    return ResolvedProfile(profile=profile, provider=provider, model=model)


def check_profile(
    resolved: ResolvedProfile, *, data_residency: DataResidency = "any", needs_tools: bool = False
) -> None:
    """Refuse before the call (llm_gateway_detail.md: `data_residency: local`, tool use).

    Raises:
        ProfileConfigurationError: the profile cannot be used for this project or agent.
    """
    if data_residency == "local" and not resolved.local:
        raise ProfileConfigurationError(
            f"data_residency is local: profile {resolved.profile!r} uses the cloud provider "
            f"{resolved.provider!r}; map it to ollama or a local openai-compatible endpoint"
        )
    if needs_tools and not resolved.supports_tools:
        raise ProfileConfigurationError(
            f"profile {resolved.profile!r} ({resolved.provider}/{resolved.model}) has no tool "
            "use, but the agent declares tools"
        )
    if resolved.provider == "anthropic-cli" and not resolved.options.get("acknowledge_cli_terms"):
        raise ProfileConfigurationError("anthropic-cli is opt-in: acknowledge_cli_terms is not set")


def downgrade_chain(profile: str, allow_downgrade: bool) -> list[str]:
    """`strong → balanced → fast` when the agent allows it, else just `profile`."""
    chain = [profile]
    while allow_downgrade and chain[-1] in DOWNGRADE:
        chain.append(DOWNGRADE[chain[-1]])
    return chain
