# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest


def test_live(client):
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.django_db
def test_ready(client):
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["checks"] == {"database": True, "redis": True}


@pytest.mark.django_db
def test_not_ready_when_redis_is_down(client, settings):
    settings.REDIS_URL = "redis://127.0.0.1:1/0"
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["redis"] is False


def test_not_ready_when_database_is_down(client, monkeypatch):
    from dexterhouse import health

    monkeypatch.setattr(health, "connection", None)
    assert health._check_database() is False
