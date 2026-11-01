# SPDX-License-Identifier: AGPL-3.0-or-later
"""The generated OpenAPI 3.1 document of REST v1 (`/api/v1/openapi.json`)."""

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_openapi_is_public_and_lists_v1():
    response = APIClient().get("/api/v1/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["openapi"] == "3.1.0"
    assert schema["info"]["title"] == "DexterHouse API"
    assert "/api/v1/projects" in schema["paths"]
    assert "/api/v1/gates/{gate_id}/decide" in schema["paths"]
    assert not any(path.startswith("/internal") for path in schema["paths"])
    assert schema["components"]["securitySchemes"]["bearerToken"]["scheme"] == "bearer"
