# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory

from dexterhouse.apps.accounts.authentication import ApiTokenAuthentication
from dexterhouse.apps.accounts.models import ApiToken, Scope
from dexterhouse.apps.accounts.services.tokens import (
    InvalidScopeError,
    create_token,
    hash_token,
    resolve_token,
)

pytestmark = pytest.mark.django_db


def test_create_stores_only_the_hash(organization, user):
    token, plaintext = create_token(
        organization=organization, user=user, name="ci", scopes=["events:read", "events:read"]
    )
    assert plaintext.startswith("dh_")
    assert token.token_hash == hash_token(plaintext)
    assert plaintext not in token.token_hash
    assert token.scopes == ["events:read"]
    assert token.has_scope(Scope.EVENTS_READ)
    assert not token.has_scope(Scope.GATES_DECIDE)


def test_unknown_scope_is_rejected(organization, user):
    with pytest.raises(InvalidScopeError, match="root"):
        create_token(organization=organization, user=user, name="x", scopes=["root"])
    assert not ApiToken.objects.exists()


def test_resolve_touches_last_used(organization, user):
    token, plaintext = create_token(organization=organization, user=user, name="ci", scopes=[])
    resolved = resolve_token(plaintext)
    assert resolved == token
    token.refresh_from_db()
    assert token.last_used_at is not None


@pytest.mark.parametrize("value", ["", "nope", "dh_wrong"])
def test_resolve_unknown(organization, user, value):
    create_token(organization=organization, user=user, name="ci", scopes=[])
    assert resolve_token(value) is None


def test_resolve_expired_or_inactive(organization, user):
    _, expired = create_token(
        organization=organization,
        user=user,
        name="old",
        scopes=[],
        expires_at=timezone.now() - timedelta(seconds=1),
    )
    assert resolve_token(expired) is None
    _, active = create_token(organization=organization, user=user, name="new", scopes=[])
    user.is_active = False
    user.save()
    assert resolve_token(active) is None


def test_drf_authentication(organization, user):
    auth = ApiTokenAuthentication()
    factory = APIRequestFactory()
    token, plaintext = create_token(organization=organization, user=user, name="ci", scopes=[])
    assert auth.authenticate(factory.get("/")) is None
    assert auth.authenticate(factory.get("/", HTTP_AUTHORIZATION="Basic abc")) is None
    assert auth.authenticate(factory.get("/", HTTP_AUTHORIZATION=f"Bearer {plaintext}")) == (
        user,
        token,
    )
    with pytest.raises(AuthenticationFailed):
        auth.authenticate(factory.get("/", HTTP_AUTHORIZATION="Bearer dh_bad"))
    assert auth.authenticate_header(factory.get("/")) == "Bearer"
