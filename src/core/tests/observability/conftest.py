# SPDX-License-Identifier: AGPL-3.0-or-later
from decimal import Decimal

import pytest

from dexterhouse.apps.gateway.models import LLMCall
from tests.workflows.conftest import make_project, real_runtime, started  # noqa: F401


@pytest.fixture
def make_call(organization):
    """Insert a priced `LLMCall` for `project` (no provider involved)."""

    def make(project, cost="0.5", **fields):
        data = {
            "organization": organization,
            "project": project,
            "provider": "fake",
            "model": "fake-model",
            "profile": "fast",
            "status": "ok",
            "input_tokens": 100,
            "output_tokens": 50,
            "cost": Decimal(cost) if cost is not None else None,
            **fields,
        }
        return LLMCall.objects.create(**data)

    return make
