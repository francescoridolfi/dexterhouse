# SPDX-License-Identifier: AGPL-3.0-or-later
"""Embedders producing L2-normalised 1024-d vectors (CD-018, CD-023, pricing_and_embeddings.md).

Order when no `embed` profile is configured: Ollama `mxbai-embed-large` if reachable, then
OpenAI `text-embedding-3-small` with `dimensions: 1024` if a key is set. Anthropic has no
embeddings. Models with another size are truncated (Matryoshka) or zero-padded.
"""

import hashlib
import math
import re
import uuid
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

import httpx2
import openai
import structlog

from dexterhouse.apps.gateway.conf import get_gateway_env
from dexterhouse.apps.gateway.models import ModelProfile
from dexterhouse.apps.gateway.providers.base import ProviderConfig, ProviderError
from dexterhouse.apps.gateway.providers.ollama import ollama_client
from dexterhouse.apps.gateway.services.profiles import (
    DataResidency,
    ProfileConfigurationError,
    ResolvedProfile,
    check_profile,
)

logger = structlog.get_logger(__name__)

DIMENSIONS = 1024
DEFAULT_OLLAMA_MODEL = "mxbai-embed-large"
DEFAULT_OPENAI_MODEL = "text-embedding-3-small"
#: Models trained with Matryoshka loss: truncation keeps quality.
MATRYOSHKA = frozenset({"text-embedding-3-small", "text-embedding-3-large", "nomic-embed-text"})
Vector = list[float]


class EmbedderUnavailableError(ProviderError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="configuration")


@runtime_checkable
class Embedder(Protocol):
    name: str  # `provider/model`, stored in `MemoryChunk.embedder`

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        """One normalised 1024-d vector per text."""
        ...


def fit(vector: Sequence[float], *, matryoshka: bool) -> Vector:
    """Bring a vector to 1024 dimensions and normalise it (L2)."""
    values = list(vector)
    if len(values) > DIMENSIONS:
        if not matryoshka:
            logger.warning("gateway.embedding_truncated", dims=len(values))
        values = values[:DIMENSIONS]
    elif len(values) < DIMENSIONS:
        logger.warning("gateway.embedding_padded", dims=len(values))
        values += [0.0] * (DIMENSIONS - len(values))
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


class OllamaEmbedder:
    def __init__(
        self, model: str = DEFAULT_OLLAMA_MODEL, config: ProviderConfig | None = None
    ) -> None:
        self.model = model
        self.name = f"ollama/{model}"
        self.client = ollama_client(config or ProviderConfig())
        self.matryoshka = model in MATRYOSHKA

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        try:
            response = self.client.post(
                "/api/embed", json={"model": self.model, "input": list(texts)}
            )
        except httpx2.TransportError as exc:
            raise ProviderError(f"ollama unreachable: {exc}", retryable=True) from exc
        if response.status_code >= 400:
            raise ProviderError(f"ollama embed {response.status_code}: {response.text[:300]}")
        return [fit(v, matryoshka=self.matryoshka) for v in response.json()["embeddings"]]


class OpenAIEmbedder:
    """`openai` (native 1024 via `dimensions`) or `openai-compatible` (fit afterwards)."""

    def __init__(
        self,
        model: str = DEFAULT_OPENAI_MODEL,
        config: ProviderConfig | None = None,
        *,
        provider: str = "openai",
    ) -> None:
        config = config or ProviderConfig()
        env = get_gateway_env()
        compatible = provider == "openai-compatible"
        self.model = model
        self.name = f"{provider}/{model}"
        self.send_dimensions = not compatible
        self.matryoshka = model in MATRYOSHKA or bool(config.options.get("matryoshka"))
        self.client = openai.OpenAI(
            api_key=config.api_key
            or (env.OPENAI_COMPATIBLE_API_KEY if compatible else env.OPENAI_API_KEY)
            or "missing",
            base_url=config.base_url
            or (env.OPENAI_COMPATIBLE_BASE_URL if compatible else env.OPENAI_BASE_URL)
            or None,
            max_retries=2,
            http_client=config.http_client,
        )

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        extra = {"dimensions": DIMENSIONS} if self.send_dimensions else {}
        try:
            response = self.client.embeddings.create(model=self.model, input=list(texts), **extra)
        except openai.APIError as exc:
            raise ProviderError(f"{self.name} embeddings failed: {exc}", retryable=True) from exc
        return [fit(item.embedding, matryoshka=self.matryoshka) for item in response.data]


class FakeEmbedder:
    """Deterministic hashed bag of words: similar texts get similar vectors (tests, CI)."""

    name = "fake/hash-1024"

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        return [self._one(text) for text in texts]

    @staticmethod
    def _one(text: str) -> Vector:
        vector = [0.0] * DIMENSIONS
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            digest = hashlib.sha256(word.encode()).digest()
            vector[int.from_bytes(digest[:4], "big") % DIMENSIONS] += 1.0
        if not any(vector):
            vector[0] = 1.0
        return fit(vector, matryoshka=True)


def build_embedder(resolved: ResolvedProfile) -> Embedder:
    config = resolved.config()
    if resolved.provider == "ollama":
        return OllamaEmbedder(resolved.model, config)
    if resolved.provider in {"openai", "openai-compatible"}:
        return OpenAIEmbedder(resolved.model, config, provider=resolved.provider)
    if resolved.provider == "fake":
        return FakeEmbedder()
    raise EmbedderUnavailableError(f"{resolved.provider} provides no embeddings")


def resolve_embedder(
    organization_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
    *,
    data_residency: DataResidency = "any",
) -> Embedder:
    """The `embed` profile if configured, else the default order of CD-023.

    Raises:
        EmbedderUnavailableError: nothing usable (UI proposes Ollama or an OpenAI key).
        ProfileConfigurationError: the configured embedder is cloud and residency is local.
    """
    rows = ModelProfile.objects.filter(organization_id=organization_id, profile="embed")
    row = (rows.filter(project_id=project_id).first() if project_id else None) or rows.filter(
        project_id__isnull=True
    ).first()
    if row is not None:
        resolved = ResolvedProfile(
            profile="embed",
            provider=row.provider,
            model=row.model,
            base_url=row.base_url,
            api_key_env=row.api_key_env,
            options=dict(row.options),
            is_local=row.is_local,
            source="organization",
        )
        check_profile(resolved, data_residency=data_residency)
        return build_embedder(resolved)
    if ollama_reachable():
        return OllamaEmbedder()
    if data_residency == "local":
        raise ProfileConfigurationError("data_residency is local and Ollama is not reachable")
    if get_gateway_env().OPENAI_API_KEY:
        return OpenAIEmbedder()
    raise EmbedderUnavailableError(
        "no embedder: start Ollama (mxbai-embed-large) or set OPENAI_API_KEY; "
        "Anthropic does not provide embeddings"
    )


def ollama_reachable(timeout_s: float = 1.0) -> bool:
    try:
        response = httpx2.get(f"{get_gateway_env().OLLAMA_BASE_URL}/api/tags", timeout=timeout_s)
    except httpx2.HTTPError:
        return False
    return response.status_code == 200
