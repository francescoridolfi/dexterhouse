# SPDX-License-Identifier: AGPL-3.0-or-later
"""MemoryChunk: an indexed piece of an artifact, gate comment or note (data_model/infra.md)."""

from django.db import models
from pgvector.django import HnswIndex, VectorField

from dexterhouse.common.models import BaseModel
from dexterhouse_schema.common import ARTIFACT_KINDS

DIMENSIONS = 1024  # CD-018: one column size for every embedder
EXTRA_KINDS = ("gate_comment", "note", "retro_lesson")
CHUNK_KINDS = tuple(sorted(ARTIFACT_KINDS)) + EXTRA_KINDS


class MemoryChunk(BaseModel):
    """`artifact_id` is the artifact (or the gate / note for comments and notes).

    Being polymorphic, `artifact_id` is a plain uuid without a foreign key.

    Chunks of one source version are written together; a newer version replaces them.
    """

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="memory_chunks"
    )
    artifact_id = models.UUIDField()
    artifact_version = models.IntegerField(default=1)
    artifact_name = models.CharField(max_length=200, blank=True, default="")
    kind = models.CharField(max_length=32, choices=[(k, k) for k in CHUNK_KINDS])
    weight = models.FloatField(default=1.0)
    chunk_index = models.IntegerField()
    heading = models.CharField(max_length=200, blank=True, default="")
    content = models.TextField()
    untrusted = models.BooleanField(default=False)  # stays wrapped in <<untrusted>> in prompts
    embedding = VectorField(dimensions=DIMENSIONS)
    embedder = models.CharField(max_length=80)

    class Meta:
        db_table = "dh_memory_chunk"
        indexes = [
            models.Index(fields=["project", "kind"], name="dh_memory_project_kind"),
            models.Index(fields=["artifact_id", "artifact_version"], name="dh_memory_artifact"),
            HnswIndex(
                name="dh_memory_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["artifact_id", "artifact_version", "embedder", "chunk_index"],
                name="dh_memory_chunk_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(kind__in=CHUNK_KINDS), name="dh_memory_kind_valid"
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.artifact_name or self.artifact_id} v{self.artifact_version} #{self.chunk_index}"
        )
