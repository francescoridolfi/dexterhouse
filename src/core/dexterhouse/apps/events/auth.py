# SPDX-License-Identifier: AGPL-3.0-or-later
"""WebSocket authentication: session cookie (AuthMiddleware) or `?token=` API token."""

from typing import Any
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from channels.security.websocket import AllowedHostsOriginValidator

from dexterhouse.apps.accounts.models import ApiToken
from dexterhouse.apps.accounts.services.tokens import resolve_token


class TokenAuthMiddleware(BaseMiddleware):
    """Put the token's user and the token itself in the scope when `?token=` is present."""

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> Any:
        query = parse_qs(scope.get("query_string", b"").decode())
        values = query.get("token")
        if values:
            token: ApiToken | None = await database_sync_to_async(resolve_token)(values[0])
            scope = dict(scope, api_token=token)
            if token is not None:
                scope["user"] = token.user
        return await super().__call__(scope, receive, send)


class OriginValidatorAllowingNonBrowsers:
    """`AllowedHostsOriginValidator`, except that requests without `Origin` pass.

    Cross-site WebSocket hijacking needs a browser, and browsers always send `Origin`; CLI and
    API clients authenticating with `?token=` usually do not, and Channels would reject them.
    """

    def __init__(self, application: Any) -> None:
        self.application = application
        self.validated = AllowedHostsOriginValidator(application)

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> Any:
        headers = dict(scope.get("headers", []))
        target = self.validated if b"origin" in headers else self.application
        return await target(scope, receive, send)
