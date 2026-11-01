# SPDX-License-Identifier: AGPL-3.0-or-later
import uuid

import pytest

from dexterhouse.apps.gateway.embeddings import FakeEmbedder
from dexterhouse.apps.gateway.models import ModelProfile

ARCHITECTURE = """# Architecture

Intro paragraph about GymBook.

## Data model

Booking has a slot, a member and a status. The waitlist is FIFO and notifies by email.

## Modules

bookings, members, notifications.
"""


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def project_id(project) -> uuid.UUID:
    return project.id


@pytest.fixture
def fake_embed_profile(organization) -> ModelProfile:
    return ModelProfile.objects.create(
        organization=organization, profile="embed", provider="fake", model="hash-1024"
    )
