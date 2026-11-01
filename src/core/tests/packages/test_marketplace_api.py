# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST v1 marketplace proxy (E-08)."""

import pytest

pytestmark = pytest.mark.django_db
HEADER = "X-Marketplace-Source"


def test_search_details_and_status(client, publish):
    publish("htmx-frontend-developer", tags=["htmx"], verified=True)
    found = client.get("/api/v1/marketplace/search?q=htmx&kind=agent&tags=htmx&verified=1")
    assert found.status_code == 200
    assert found[HEADER] == "index"
    (result,) = found.json()["results"]
    assert result["description"] == "htmx-frontend-developer"  # unwrapped for people
    detail = client.get("/api/v1/marketplace/packages/htmx-frontend-developer")
    assert (detail.status_code, detail[HEADER]) == (200, "index")
    assert detail.json()["readme"].startswith("# htmx-frontend-developer")
    assert client.get("/api/v1/marketplace/packages/ghost").status_code == 404
    status = client.get("/api/v1/marketplace/status")
    assert (status.json()["status"], status[HEADER]) == ("reachable", "index")


def test_unreachable_and_invalid_parameters(client):
    found = client.get("/api/v1/marketplace/search?q=x")
    assert (found.status_code, found[HEADER]) == (200, "unreachable")
    detail = client.get("/api/v1/marketplace/packages/x")
    assert detail.status_code == 503
    assert detail.json()["type"].endswith("marketplace-unavailable")
    assert client.get("/api/v1/marketplace/search?kind=theme").status_code == 400
    assert client.get("/api/v1/marketplace/search?min_rating=high").status_code == 400
    assert client.get("/api/v1/marketplace/status").json()["status"] == "unreachable"


def test_meta_announces_the_marketplace(client):
    assert client.get("/api/v1/meta").json()["features"]["marketplace"] is True


def test_anonymous_requests_are_refused(db):
    from rest_framework.test import APIClient

    assert APIClient().get("/api/v1/marketplace/status").status_code in (401, 403)
