# SPDX-License-Identifier: AGPL-3.0-or-later
"""`memory.search`: cosine similarity in one project, weighted, same embedder only."""

import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

import structlog
from django.db.models import F, FloatField, Value
from django.db.models.functions import Cast
from pgvector.django import CosineDistance

from dexterhouse.apps.gateway.embeddings import Embedder
from dexterhouse.apps.memory.models import MemoryChunk

logger = structlog.get_logger(__name__)

REINDEX_REQUIRED = "reindex_required"


@dataclass(frozen=True)
class Hit:
    artifact_id: str
    kind: str
    name: str
    version: int
    chunk_index: int
    heading: str
    content: str
    score: float  # cosine similarity
    weight: float
    untrusted: bool

    @property
    def ranked(self) -> float:
        return self.score * self.weight

    def as_dict(self) -> dict[str, Any]:
        """Shape returned by the MCP tool (contracts/tools/memory.md)."""
        data = asdict(self)
        return {
            "artifact": {
                "id": data.pop("artifact_id"),
                "kind": data.pop("kind"),
                "name": data.pop("name"),
                "version": data.pop("version"),
            },
            **data,
            "score": round(self.score, 4),
        }


@dataclass(frozen=True)
class SearchResult:
    hits: list[Hit]
    warnings: list[str] = field(default_factory=list)


def search(
    *,
    project_id: uuid.UUID,
    query: str,
    embedder: Embedder,
    k: int = 8,
    kinds: Iterable[str] | None = None,
    min_score: float = 0.3,
    exclude_artifacts: Iterable[uuid.UUID | str] = (),
) -> SearchResult:
    """Top-`k` chunks with similarity ≥ `min_score`, ranked by similarity * weight.

    Only chunks embedded with the current embedder are comparable; when the project has
    chunks from another one, the result is empty with the `reindex_required` warning.
    """
    chunks = MemoryChunk.objects.filter(project_id=project_id)
    same = chunks.filter(embedder=embedder.name)
    if not same.exists():
        if chunks.exists():
            logger.warning(
                "memory.reindex_required", project_id=str(project_id), embedder=embedder.name
            )
            return SearchResult(hits=[], warnings=[REINDEX_REQUIRED])
        return SearchResult(hits=[])
    if kinds:
        same = same.filter(kind__in=list(kinds))
    excluded = [str(a) for a in exclude_artifacts]
    if excluded:
        same = same.exclude(artifact_id__in=excluded)
    vector = embedder.embed([query])[0]
    rows = (
        same.annotate(score=Value(1.0) - Cast(CosineDistance("embedding", vector), FloatField()))
        .filter(score__gte=min_score)
        .annotate(ranked=F("score") * F("weight"))
        .order_by("-ranked", "artifact_id", "chunk_index")[: max(1, min(k, 50))]
    )
    hits = [
        Hit(
            artifact_id=str(row.artifact_id),
            kind=row.kind,
            name=row.artifact_name,
            version=row.artifact_version,
            chunk_index=row.chunk_index,
            heading=row.heading,
            content=row.content,
            score=float(row.score),
            weight=row.weight,
            untrusted=row.untrusted,
        )
        for row in rows
    ]
    return SearchResult(hits=hits)


def recent(
    *, project_id: uuid.UUID, kinds: Iterable[str] | None = None, limit: int = 10
) -> list[dict[str, Any]]:
    """`memory.recent`: latest indexed sources (one entry per artifact version)."""
    chunks = MemoryChunk.objects.filter(project_id=project_id, chunk_index=0)
    if kinds:
        chunks = chunks.filter(kind__in=list(kinds))
    return [
        {
            "artifact": {
                "id": str(c.artifact_id),
                "kind": c.kind,
                "name": c.artifact_name,
                "version": c.artifact_version,
            },
            "indexed_at": c.created_at.isoformat(),
            "excerpt": c.content[:300],
        }
        for c in chunks.order_by("-created_at")[: max(1, min(limit, 50))]
    ]
