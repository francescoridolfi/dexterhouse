# SPDX-License-Identifier: AGPL-3.0-or-later
"""Re-embed a project's memory with another embedder (pricing_and_embeddings.md)."""

import uuid
from dataclasses import dataclass

from django.db import transaction

from dexterhouse.apps.gateway.embeddings import Embedder
from dexterhouse.apps.memory.models import MemoryChunk

BATCH = 64


@dataclass(frozen=True)
class ReindexResult:
    project_id: uuid.UUID
    chunks: int
    replaced: int


def reindex_project(
    project_id: uuid.UUID, embedder: Embedder, *, batch: int = BATCH, dry_run: bool = False
) -> ReindexResult:
    """Embed every current chunk again with `embedder`, then swap them in one transaction.

    Until the swap, searches keep using the old chunks.
    """
    old = list(
        MemoryChunk.objects.filter(project_id=project_id)
        .exclude(embedder=embedder.name)
        .order_by("artifact_id", "artifact_version", "chunk_index")
    )
    if dry_run or not old:
        return ReindexResult(project_id, len(old), 0)
    fresh: list[MemoryChunk] = []
    for start in range(0, len(old), batch):
        group = old[start : start + batch]
        texts = [f"{c.heading}\n{c.content}" if c.heading else c.content for c in group]
        for chunk, vector in zip(group, embedder.embed(texts), strict=True):
            fresh.append(
                MemoryChunk(
                    project_id=chunk.project_id,
                    artifact_id=chunk.artifact_id,
                    artifact_version=chunk.artifact_version,
                    artifact_name=chunk.artifact_name,
                    kind=chunk.kind,
                    weight=chunk.weight,
                    chunk_index=chunk.chunk_index,
                    heading=chunk.heading,
                    content=chunk.content,
                    untrusted=chunk.untrusted,
                    embedding=vector,
                    embedder=embedder.name,
                )
            )
    with transaction.atomic():
        MemoryChunk.objects.filter(project_id=project_id, embedder=embedder.name).delete()
        replaced, _ = MemoryChunk.objects.filter(id__in=[c.id for c in old]).delete()
        MemoryChunk.objects.bulk_create(fresh)
    return ReindexResult(project_id, len(fresh), replaced)
