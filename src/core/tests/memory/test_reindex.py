# SPDX-License-Identifier: AGPL-3.0-or-later
import uuid
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from dexterhouse.apps.gateway.embeddings import FakeEmbedder
from dexterhouse.apps.memory.models import MemoryChunk
from dexterhouse.apps.memory.services.indexing import index_artifact
from dexterhouse.apps.memory.services.search import search

from .conftest import ARCHITECTURE

pytestmark = pytest.mark.django_db


class OldEmbedder(FakeEmbedder):
    name = "ollama/old-model"


def test_reindex_switches_embedder(organization, project_id, fake_embed_profile):
    index_artifact(
        organization_id=organization.id,
        project_id=project_id,
        artifact_id=uuid.uuid4(),
        version=1,
        kind="architecture",
        content=ARCHITECTURE,
        embedder=OldEmbedder(),
    )
    assert search(project_id=project_id, query="waitlist", embedder=FakeEmbedder()).warnings
    out = StringIO()
    call_command("memory", "reindex", "--project", str(project_id), "--dry-run", stdout=out)
    assert "would re-embed 3 chunks" in out.getvalue()
    call_command("memory", "reindex", "--all", stdout=out)
    assert set(MemoryChunk.objects.values_list("embedder", flat=True)) == {"fake/hash-1024"}
    hits = search(
        project_id=project_id, query="waitlist FIFO email", embedder=FakeEmbedder(), min_score=0.1
    ).hits
    assert hits[0].heading == "Data model"
    call_command("memory", "reindex", "--all", "--embedder", "fake/hash", stdout=out)
    assert MemoryChunk.objects.count() == 3
    with pytest.raises(CommandError):
        call_command("memory", "reindex", "--all", "--embedder", "fake")
