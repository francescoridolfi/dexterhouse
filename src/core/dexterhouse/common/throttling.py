# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST rate limits (contracts/api/README.md, T7): per token or user, per IP when anonymous.

Rates come from `settings.API_THROTTLE_RATES` at request time (`None` switches a scope off),
so tests and installations change them without redefining the classes. Counters live in the
default cache (Redis in the compose stack, shared by every web worker).
"""

from typing import TYPE_CHECKING, Any

from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle

if TYPE_CHECKING:  # DRF imports this module while loading its settings: no views here
    from rest_framework.request import Request


class _SettingsRateThrottle(SimpleRateThrottle):
    def get_rate(self) -> str | None:
        return settings.API_THROTTLE_RATES.get(self.scope)

    def get_ident(self, request: "Request") -> str:
        """Client IP behind `API_TRUSTED_PROXIES` reverse proxies (nginx, Caddy)."""
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        proxies = settings.API_TRUSTED_PROXIES
        if forwarded and proxies > 0:
            addresses = [a.strip() for a in forwarded.split(",") if a.strip()]
            if addresses:
                return addresses[-min(proxies, len(addresses))]
        return request.META.get("REMOTE_ADDR", "")


class ClientRateThrottle(_SettingsRateThrottle):
    """`600/min` per API token, or per user for browser sessions."""

    scope = "client"

    def get_cache_key(self, request: "Request", view: Any) -> str | None:
        from dexterhouse.apps.accounts.models import ApiToken

        if isinstance(request.auth, ApiToken):
            ident = f"token:{request.auth.pk}"
        elif request.user and request.user.is_authenticated:
            ident = f"user:{request.user.pk}"
        else:
            return None
        return self.cache_format % {"scope": self.scope, "ident": ident}


class AnonRateThrottle(_SettingsRateThrottle):
    """`60/min` per IP for unauthenticated requests."""

    scope = "anon"

    def get_cache_key(self, request: "Request", view: Any) -> str | None:
        if request.user and request.user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class LoginRateThrottle(_SettingsRateThrottle):
    """Password attempts per IP, on top of the anonymous limit."""

    scope = "login"

    def get_cache_key(self, request: "Request", view: Any) -> str | None:
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}
