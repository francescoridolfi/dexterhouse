# SPDX-License-Identifier: AGPL-3.0-or-later
"""`Idempotency-Key` on creating POSTs: replay, reuse with another body, in progress."""

import pytest
from django.core.cache import cache

from dexterhouse.apps.projects.models import Note, Project
from dexterhouse.common.api import idempotency

pytestmark = pytest.mark.django_db
BODY = {"name": "GymBook", "brief": "A gym app.", "budget": "5"}


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def post(client, path, body, key="k-1"):
    return client.post(path, body, format="json", HTTP_IDEMPOTENCY_KEY=key)


def test_retry_with_the_same_key_replays_the_first_response(client):
    first = post(client, "/api/v1/projects", BODY)
    again = post(client, "/api/v1/projects", BODY)
    assert first.status_code == again.status_code == 201
    assert again.json()["id"] == first.json()["id"]
    assert again["Idempotent-Replayed"] == "true"
    assert Project.objects.count() == 1


def test_without_a_key_each_post_creates(client):
    client.post("/api/v1/projects", BODY, format="json")
    client.post("/api/v1/projects", BODY, format="json")
    assert Project.objects.count() == 2


def test_same_key_other_body_is_422(client):
    post(client, "/api/v1/projects", BODY)
    response = post(client, "/api/v1/projects", {**BODY, "name": "Other"})
    assert response.status_code == 422
    assert response.json()["type"].endswith("/idempotency-key-reused")


def test_keys_are_per_client(client, make_member):
    other = make_member("member", "grace")
    post(client, "/api/v1/projects", BODY)
    assert post(other, "/api/v1/projects", BODY).status_code == 201
    assert Project.objects.count() == 2


def test_key_in_progress_is_409(client, monkeypatch):
    monkeypatch.setattr(idempotency.cache, "add", lambda *args, **kwargs: False)
    monkeypatch.setattr(idempotency.cache, "get", lambda key: {"fingerprint": None, "done": False})
    monkeypatch.setattr(idempotency, "_fingerprint", lambda request: None)
    assert post(client, "/api/v1/projects", BODY).status_code == 409


def test_errors_are_not_kept(client):
    bad = post(client, "/api/v1/projects", {"name": ""})
    assert bad.status_code == 400
    response = post(client, "/api/v1/projects", {"name": ""})
    assert response.status_code == 400
    assert "Idempotent-Replayed" not in response


def test_invalid_key_is_400(client):
    assert post(client, "/api/v1/projects", BODY, key="x" * 300).status_code == 400


def test_notes_use_it_too(client, project):
    path = f"/api/v1/projects/{project.id}/notes"
    post(client, path, {"content": "Use Postgres."}, key="n")
    post(client, path, {"content": "Use Postgres."}, key="n")
    assert Note.objects.filter(project=project).count() == 1
