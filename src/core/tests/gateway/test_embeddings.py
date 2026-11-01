# SPDX-License-Identifier: AGPL-3.0-or-later
"""1024-d embedders and the default order of CD-023."""

import json
import math

import httpx2
import pytest

from dexterhouse.apps.gateway import embeddings
from dexterhouse.apps.gateway.conf import get_gateway_env
from dexterhouse.apps.gateway.embeddings import (
    DIMENSIONS,
    EmbedderUnavailableError,
    FakeEmbedder,
    OllamaEmbedder,
    OpenAIEmbedder,
    fit,
    resolve_embedder,
)
from dexterhouse.apps.gateway.models import ModelProfile
from dexterhouse.apps.gateway.providers import ProviderConfig, ProviderError
from dexterhouse.apps.gateway.services.profiles import ProfileConfigurationError


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def mock_client(handler) -> httpx2.Client:
    return httpx2.Client(transport=httpx2.MockTransport(handler), base_url="http://ollama.test")


def test_fit_pads_truncates_and_normalises():
    padded = fit([3.0, 4.0], matryoshka=False)
    assert len(padded) == DIMENSIONS
    assert padded[:2] == [0.6, 0.8]
    truncated = fit([1.0] * 1536, matryoshka=True)
    assert len(truncated) == DIMENSIONS
    assert math.isclose(sum(v * v for v in truncated), 1.0)
    assert len(fit([1.0] * 2048, matryoshka=False)) == DIMENSIONS


def test_fake_embedder_is_deterministic_and_semantic():
    fake = FakeEmbedder()
    a, b, c, empty = fake.embed(
        ["waitlist is FIFO with email", "the waitlist is FIFO", "pricing in euro", "!!"]
    )
    assert a == fake.embed(["waitlist is FIFO with email"])[0]
    assert cosine(a, b) > cosine(a, c)
    assert math.isclose(sum(v * v for v in empty), 1.0)


def test_ollama_embedder():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.update(json.loads(request.content))
        return httpx2.Response(200, json={"embeddings": [[0.5] * 1024, [1.0] * 768]})

    embedder = OllamaEmbedder(config=ProviderConfig(http_client=mock_client(handler)))
    vectors = embedder.embed(["a", "b"])
    assert seen == {"model": "mxbai-embed-large", "input": ["a", "b"]}
    assert embedder.name == "ollama/mxbai-embed-large"
    assert all(len(v) == DIMENSIONS for v in vectors)
    broken = OllamaEmbedder(
        config=ProviderConfig(http_client=mock_client(lambda r: httpx2.Response(404, text="no")))
    )
    with pytest.raises(ProviderError, match="404"):
        broken.embed(["a"])

    def refuse(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused")

    with pytest.raises(ProviderError, match="unreachable"):
        OllamaEmbedder(config=ProviderConfig(http_client=mock_client(refuse))).embed(["a"])


@pytest.mark.parametrize(
    ("provider", "dimensions"), [("openai", 1024), ("openai-compatible", None)]
)
def test_openai_embedders(provider, dimensions):
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.update(json.loads(request.content))
        data = [{"object": "embedding", "index": 0, "embedding": [0.1] * (dimensions or 1536)}]
        return httpx2.Response(
            200,
            json={
                "object": "list",
                "data": data,
                "model": "m",
                "usage": {"prompt_tokens": 1, "total_tokens": 1},
            },
        )

    config = ProviderConfig(
        api_key="k", base_url="http://embed.test/v1", http_client=mock_client(handler)
    )
    embedder = OpenAIEmbedder("text-embedding-3-small", config, provider=provider)
    vectors = embedder.embed(["x"])
    assert seen.get("dimensions") == dimensions
    assert len(vectors[0]) == DIMENSIONS
    assert embedder.name == f"{provider}/text-embedding-3-small"


@pytest.mark.django_db
class TestResolve:
    @pytest.fixture(autouse=True)
    def _no_env(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setattr(embeddings, "ollama_reachable", lambda timeout_s=1.0: False)
        get_gateway_env.cache_clear()
        yield
        get_gateway_env.cache_clear()

    def test_profile_row_wins(self, organization):
        ModelProfile.objects.create(
            organization=organization, profile="embed", provider="fake", model="hash"
        )
        assert isinstance(resolve_embedder(organization.id), FakeEmbedder)

    def test_nothing_configured(self, organization):
        with pytest.raises(EmbedderUnavailableError, match="Anthropic does not provide"):
            resolve_embedder(organization.id)
        with pytest.raises(ProfileConfigurationError):
            resolve_embedder(organization.id, data_residency="local")

    def test_default_order(self, organization, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")  # pragma: allowlist secret
        get_gateway_env.cache_clear()
        assert resolve_embedder(organization.id).name == "openai/text-embedding-3-small"
        monkeypatch.setattr(embeddings, "ollama_reachable", lambda timeout_s=1.0: True)
        assert resolve_embedder(organization.id).name == "ollama/mxbai-embed-large"

    def test_residency_blocks_cloud_embedder(self, organization):
        ModelProfile.objects.create(
            organization=organization,
            profile="embed",
            provider="openai",
            model="text-embedding-3-small",
        )
        with pytest.raises(ProfileConfigurationError):
            resolve_embedder(organization.id, data_residency="local")
        assert resolve_embedder(organization.id).name == "openai/text-embedding-3-small"

    def test_cli_has_no_embeddings(self):
        from dexterhouse.apps.gateway.services.profiles import ResolvedProfile

        with pytest.raises(EmbedderUnavailableError):
            embeddings.build_embedder(
                ResolvedProfile(profile="embed", provider="anthropic", model="x")
            )


def test_ollama_reachable_is_false_when_down(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:9")
    get_gateway_env.cache_clear()
    assert embeddings.ollama_reachable(timeout_s=0.2) is False
    get_gateway_env.cache_clear()
