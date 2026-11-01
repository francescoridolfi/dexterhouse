# SPDX-License-Identifier: AGPL-3.0-or-later
"""DRF authentication with `Authorization: Bearer <token>`."""

from rest_framework import authentication, exceptions
from rest_framework.request import Request

from dexterhouse.apps.accounts.models import ApiToken, User
from dexterhouse.apps.accounts.services.tokens import resolve_token


class ApiTokenAuthentication(authentication.BaseAuthentication):
    """Authenticate API/CLI calls; `request.auth` is the `ApiToken` (scopes)."""

    keyword = "Bearer"

    def authenticate(self, request: Request) -> tuple[User, ApiToken] | None:
        header = authentication.get_authorization_header(request).decode("latin-1")
        if not header:
            return None
        keyword, _, value = header.partition(" ")
        if keyword != self.keyword:
            return None
        token = resolve_token(value.strip())
        if token is None:
            raise exceptions.AuthenticationFailed("invalid or expired token")
        return token.user, token

    def authenticate_header(self, request: Request) -> str:
        return self.keyword
