# SPDX-License-Identifier: AGPL-3.0-or-later
"""Provider registry; concrete cloud/local providers arrive in the gateway epic."""

from collections.abc import Callable

from dexterhouse.apps.gateway.providers.base import Provider, ProviderError, collect
from dexterhouse.apps.gateway.providers.fake import FakeProvider

PROVIDERS: dict[str, Callable[[], Provider]] = {"fake": FakeProvider}


class UnknownProviderError(LookupError):
    """No provider is registered under this name."""


def get_provider(name: str) -> Provider:
    try:
        return PROVIDERS[name]()
    except KeyError:
        raise UnknownProviderError(name) from None


__all__ = ["PROVIDERS", "FakeProvider", "Provider", "ProviderError", "collect", "get_provider"]
