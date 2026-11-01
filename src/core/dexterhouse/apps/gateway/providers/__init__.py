# SPDX-License-Identifier: AGPL-3.0-or-later
"""Provider registry: a factory per provider id, called with a `ProviderConfig`."""

from collections.abc import Callable

from dexterhouse.apps.gateway.providers.anthropic import AnthropicProvider
from dexterhouse.apps.gateway.providers.anthropic_cli import AnthropicCliProvider
from dexterhouse.apps.gateway.providers.base import (
    Capabilities,
    Provider,
    ProviderConfig,
    ProviderError,
    collect,
)
from dexterhouse.apps.gateway.providers.fake import FakeProvider, configured_responder
from dexterhouse.apps.gateway.providers.ollama import OllamaProvider
from dexterhouse.apps.gateway.providers.openai import OpenAICompatibleProvider, OpenAIProvider

ProviderFactory = Callable[[ProviderConfig], Provider]

PROVIDERS: dict[str, ProviderFactory] = {
    "anthropic": AnthropicProvider,
    "anthropic-cli": AnthropicCliProvider,
    "openai": OpenAIProvider,
    "openai-compatible": OpenAICompatibleProvider,
    "ollama": OllamaProvider,
    "fake": lambda config: FakeProvider(responder=configured_responder()),
}

#: Providers whose data never leaves the installation, whatever the profile says.
LOCAL_PROVIDERS = frozenset({"ollama", "fake"})


class UnknownProviderError(LookupError):
    """No provider is registered under this name."""


def get_provider(name: str, config: ProviderConfig | None = None) -> Provider:
    try:
        factory = PROVIDERS[name]
    except KeyError:
        raise UnknownProviderError(name) from None
    return factory(config or ProviderConfig())


__all__ = [
    "LOCAL_PROVIDERS",
    "PROVIDERS",
    "Capabilities",
    "FakeProvider",
    "Provider",
    "ProviderConfig",
    "ProviderError",
    "UnknownProviderError",
    "collect",
    "get_provider",
]
