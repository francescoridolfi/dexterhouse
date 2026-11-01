# SPDX-License-Identifier: AGPL-3.0-or-later
"""Index artifacts, gate comments and notes into `MemoryChunk` (F-013).

Incremental by version: indexing (artifact, version) again with the same embedder is a
no-op; a newer version replaces the chunks of older ones in one transaction. Gate comments
and retrospective lessons weigh 1.5 so they rank above ordinary chunks.
"""

import re
import uuid
from dataclasses import dataclass
from typing import Any

import structlog
from django.db import transaction

from dexterhouse.apps.gateway.embeddings import Embedder, resolve_embedder
from dexterhouse.apps.memory.models import MemoryChunk
from dexterhouse.apps.memory.services.chunking import Chunk, chunk_markdown, chunk_structured

logger = structlog.get_logger(__name__)

WEIGHTS: dict[str, float] = {"gate_comment": 1.5, "retro_lesson": 1.5}
_LESSON = re.compile(r"lesson", re.IGNORECASE)
EMBED_BATCH = 64


@dataclass(frozen=True)
class IndexResult:
    created: int
    skipped: bool = False
    replaced: int = 0


def index_artifact(
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    artifact_id: uuid.UUID,
    version: int,
    kind: str,
    name: str = "",
    content: str | None = None,
    data: Any = None,
    untrusted: bool = False,
    embedder: Embedder | None = None,
) -> IndexResult:
    """Chunk, embed and store one artifact version (Markdown `content` or structured `data`).

    For `retrospective` artifacts, sections whose heading mentions lessons become
    `retro_lesson` chunks with the higher weight.
    """
    embedder = embedder or resolve_embedder(organization_id, project_id)
    existing = MemoryChunk.objects.filter(artifact_id=artifact_id, embedder=embedder.name)
    if existing.filter(artifact_version__gte=version).exists():
        return IndexResult(created=0, skipped=True)
    chunks = chunk_markdown(content or "") if data is None else chunk_structured(data)
    kinds = [
        "retro_lesson" if kind == "retrospective" and _LESSON.search(c.heading) else kind
        for c in chunks
    ]
    vectors = _embed(embedder, chunks)
    rows = [
        MemoryChunk(
            project_id=project_id,
            artifact_id=artifact_id,
            artifact_version=version,
            artifact_name=name[:200],
            kind=chunk_kind,
            weight=WEIGHTS.get(chunk_kind, 1.0),
            chunk_index=index,
            heading=chunk.heading,
            content=chunk.content,
            untrusted=untrusted,
            embedding=vector,
            embedder=embedder.name,
        )
        for index, (chunk, chunk_kind, vector) in enumerate(
            zip(chunks, kinds, vectors, strict=True)
        )
    ]
    with transaction.atomic():
        replaced, _ = MemoryChunk.objects.filter(
            artifact_id=artifact_id, artifact_version__lt=version
        ).delete()
        MemoryChunk.objects.bulk_create(rows)
    logger.info("memory.indexed", artifact_id=str(artifact_id), version=version, chunks=len(rows))
    return IndexResult(created=len(rows), replaced=replaced)


def index_comment(
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    source_id: uuid.UUID,
    text: str,
    kind: str = "gate_comment",
    name: str = "",
    embedder: Embedder | None = None,
) -> IndexResult:
    """A gate comment (weight 1.5) or a user note, indexed as a one-version source."""
    if kind not in {"gate_comment", "note"}:
        raise ValueError(f"unsupported comment kind {kind!r}")
    return index_artifact(
        organization_id=organization_id,
        project_id=project_id,
        artifact_id=source_id,
        version=1,
        kind=kind,
        name=name or kind,
        content=text,
        embedder=embedder,
    )


def _embed(embedder: Embedder, chunks: list[Chunk]) -> list[list[float]]:
    texts = [f"{c.heading}\n{c.content}" if c.heading else c.content for c in chunks]
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):
        vectors += embedder.embed(texts[start : start + EMBED_BATCH])
    return vectors
