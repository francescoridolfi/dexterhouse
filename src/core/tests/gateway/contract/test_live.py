# SPDX-License-Identifier: AGPL-3.0-or-later
"""Opt-in checks against real providers: never run in CI.

    DH_LIVE_TESTS=1 ANTHROPIC_API_KEY=... uv run pytest src/core/tests/gateway/contract/test_live.py

Each provider runs only when its credentials are set (see cassettes/README.md). With
DH_RECORD_CASSETTES=1 the HTTP responses are written to `cassettes/live/` in the cassette
format, ready to replace the hand-written ones after review (strip ids and secrets first).
"""

import json
import os
from pathlib import Path

import httpx2
import pytest

from dexterhouse.apps.gateway.conf import get_gateway_env
from dexterhouse.apps.gateway.embeddings import ollama_reachable
from dexterhouse.apps.gateway.providers import ProviderConfig, collect, get_provider

from .conftest import CASSETTES, make_request

pytestmark = pytest.mark.skipif(not os.environ.get("DH_LIVE_TESTS"), reason="DH_LIVE_TESTS not set")

LIVE = {
    "anthropic": ("ANTHROPIC_API_KEY", "claude-haiku-5-5"),
    "openai": ("OPENAI_API_KEY", "gpt-5-mini"),
    "openai-compatible": (
        "OPENAI_COMPATIBLE_BASE_URL",
        os.environ.get("DH_LIVE_COMPATIBLE_MODEL", ""),
    ),
    "ollama": ("", os.environ.get("DH_LIVE_OLLAMA_MODEL", "qwen3:14b")),
    "anthropic-cli": ("DH_LIVE_CLI", "claude-haiku-5-5"),
}


class Recording(httpx2.BaseTransport):
    def __init__(self, name: str) -> None:
        self.inner = httpx2.HTTPTransport()
        self.name = name

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        response = self.inner.handle_request(request)
        body = response.read().decode()
        out = CASSETTES / "live" / f"{self.name}.json"
        out.parent.mkdir(exist_ok=True)
        headers = {"content-type": response.headers.get("content-type", "")}
        out.write_text(
            json.dumps(
                {"status": response.status_code, "headers": headers, "body": body.split("\n")},
                indent=2,
            ),
            encoding="utf-8",
        )
        return httpx2.Response(
            response.status_code, headers=response.headers, content=body.encode()
        )


def _provider(name: str, scenario: str):
    env, model = LIVE[name]
    if name == "ollama" and not ollama_reachable():
        pytest.skip("Ollama not reachable")
    if env and not os.environ.get(env):
        pytest.skip(f"{env} not set")
    if not model:
        pytest.skip("no model configured")
    get_gateway_env.cache_clear()
    client = None
    if os.environ.get("DH_RECORD_CASSETTES") and name != "anthropic-cli":
        base = get_gateway_env().OLLAMA_BASE_URL if name == "ollama" else None
        client = httpx2.Client(
            transport=Recording(f"{name}-{scenario}"), base_url=base or "", timeout=120
        )
    return get_provider(name, ProviderConfig(http_client=client, options={"timeout_s": 180})), model


@pytest.mark.parametrize("name", list(LIVE))
def test_live_text_and_tool_use(name: str) -> None:
    provider, model = _provider(name, "tool_use")
    request = make_request(model)
    request.messages[1].parts[
        0
    ].text = "Call the memory search tool once with query 'booking rules', then stop."
    result = collect(provider.stream(request), provider=name, model=model)
    assert result.stop_reason in {"tool_use", "end"}
    assert result.usage.input > 0
    if result.stop_reason == "tool_use":
        call = next(p for p in result.message.parts if p.kind == "tool_call")
        assert call.name == "memory.search"
        assert isinstance(call.args, dict)


def test_cassette_dir_exists() -> None:
    assert Path(CASSETTES).is_dir()
