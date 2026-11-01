# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST rate limits (T7, ST-21's REST half): 429 problem with Retry-After, per client."""

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from dexterhouse.apps.accounts.services.tokens import create_token

pytestmark = pytest.mark.django_db


@pytest.fixture
def rates(settings):
    cache.clear()
    settings.API_THROTTLE_RATES = {"client": "3/min", "anon": "2/min", "login": "1/min"}
    yield settings
    cache.clear()


def test_session_user_gets_429_with_retry_after(rates, client):
    statuses = [client.get("/api/v1/auth/me").status_code for _ in range(4)]
    assert statuses == [200, 200, 200, 429]
    response = client.get("/api/v1/auth/me")
    assert response["Content-Type"] == "application/problem+json"
    assert response.json()["type"].endswith("/rate-limited")
    assert int(response["Retry-After"]) >= 1


def test_tokens_have_their_own_bucket(rates, client, organization, user):
    for _ in range(3):
        client.get("/api/v1/auth/me")
    _, plaintext = create_token(organization=organization, user=user, name="ci", scopes=[])
    api = APIClient(HTTP_AUTHORIZATION=f"Bearer {plaintext}")
    assert api.get("/api/v1/auth/me").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 429


def test_login_is_limited_per_forwarded_ip(rates, user):
    api = APIClient()
    body = {"username": "ada", "password": "wrong"}  # pragma: allowlist secret
    first = api.post("/api/v1/auth/login", body, format="json", HTTP_X_FORWARDED_FOR="10.0.0.1")
    second = api.post("/api/v1/auth/login", body, format="json", HTTP_X_FORWARDED_FOR="10.0.0.1")
    other = api.post("/api/v1/auth/login", body, format="json", HTTP_X_FORWARDED_FOR="10.0.0.2")
    assert (first.status_code, second.status_code, other.status_code) == (401, 429, 401)


def test_spoofed_forwarded_for_does_not_escape_the_limit(rates, user):
    api = APIClient()
    body = {"username": "ada", "password": "wrong"}  # pragma: allowlist secret
    for spoof in ("1.1.1.1", "2.2.2.2"):
        # nginx appends the real address: "<client-supplied>, 10.0.0.9"
        response = api.post(
            "/api/v1/auth/login", body, format="json", HTTP_X_FORWARDED_FOR=f"{spoof}, 10.0.0.9"
        )
    assert response.status_code == 429


def test_rates_off_means_no_limit(settings, client):
    settings.API_THROTTLE_RATES = {"client": None, "anon": None, "login": None}
    assert all(client.get("/api/v1/auth/me").status_code == 200 for _ in range(5))


def test_without_trusted_proxies_the_remote_address_counts(rates, user):
    rates.API_TRUSTED_PROXIES = 0
    api = APIClient()
    body = {"username": "ada", "password": "wrong"}  # pragma: allowlist secret
    api.post("/api/v1/auth/login", body, format="json", HTTP_X_FORWARDED_FOR="1.1.1.1")
    response = api.post("/api/v1/auth/login", body, format="json", HTTP_X_FORWARDED_FOR="2.2.2.2")
    assert response.status_code == 429
