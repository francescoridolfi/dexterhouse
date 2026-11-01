# SPDX-License-Identifier: AGPL-3.0-or-later
import uuid
from collections.abc import Iterator

import pytest

from dexterhouse.apps.events.schemas import Actor
from dexterhouse.apps.events.services import streams


@pytest.fixture
def project_id() -> Iterator[uuid.UUID]:
    """A fresh project id; its Redis stream is deleted afterwards."""
    value = uuid.uuid4()
    yield value
    streams.get_client().delete(streams.stream_key(value))


@pytest.fixture
def system() -> Actor:
    return Actor(type="system", name="engine")
