# SPDX-License-Identifier: AGPL-3.0-or-later
"""Create and resolve API tokens; the plaintext is returned once and never stored."""

import hashlib
import secrets
from datetime import datetime

from django.utils import timezone

from dexterhouse.apps.accounts.models import ApiToken, Organization, Scope, User

# Public, recognisable prefix (helps secret scanners), not a secret itself.
TOKEN_PREFIX = "dh_"  # noqa: S105 # nosec B105


class InvalidScopeError(ValueError):
    """A requested scope is not in the catalogue."""


def hash_token(plaintext: str) -> str:
    """sha256 hex digest of a token."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def create_token(
    *,
    organization: Organization,
    user: User,
    name: str,
    scopes: list[str],
    expires_at: datetime | None = None,
) -> tuple[ApiToken, str]:
    """Create a token and return it with its plaintext value (shown to the user once)."""
    unknown = sorted(set(scopes) - set(Scope.values))
    if unknown:
        raise InvalidScopeError(f"unknown scopes: {', '.join(unknown)}")
    plaintext = TOKEN_PREFIX + secrets.token_urlsafe(32)
    token = ApiToken.objects.create(
        organization=organization,
        user=user,
        name=name,
        token_hash=hash_token(plaintext),
        scopes=sorted(set(scopes)),
        expires_at=expires_at,
    )
    return token, plaintext


def resolve_token(plaintext: str) -> ApiToken | None:
    """Return the active token matching `plaintext` and touch `last_used_at`, or None."""
    if not plaintext.startswith(TOKEN_PREFIX):
        return None
    token = (
        ApiToken.objects.select_related("user", "organization")
        .filter(token_hash=hash_token(plaintext), user__is_active=True)
        .first()
    )
    now = timezone.now()
    if token is None or (token.expires_at is not None and token.expires_at <= now):
        return None
    ApiToken.objects.filter(pk=token.pk).update(last_used_at=now)
    return token
