# SPDX-License-Identifier: AGPL-3.0-or-later
"""generate(): profiles, residency, retries, circuit breaker, downgrade, idempotency."""

import pytest
from django.core.exceptions import ValidationError

from dexterhouse.apps.events.models import Event
from dexterhouse.apps.gateway.messages import Message, TextPart, ToolSpec
from dexterhouse.apps.gateway.models import CallStatus, LLMCall, ModelProfile
from dexterhouse.apps.gateway.providers import FakeProvider
from dexterhouse.apps.gateway.providers.fake import FakeResponse
from dexterhouse.apps.gateway.services import gateway
from dexterhouse.apps.gateway.services.gateway import (
    CallContext,
    ProviderUnavailableError,
    generate,
)
from dexterhouse.apps.gateway.services.profiles import (
    ProfileConfigurationError,
    downgrade_chain,
    resolve_profile,
)
from dexterhouse.apps.gateway.services.resilience import FAILURES, OPEN_S, CircuitBreaker

pytestmark = pytest.mark.django_db

MESSAGES = [Message(role="user", parts=[TextPart(text="hi")])]
TOOL = ToolSpec(name="memory.search", description="d", input_schema={"type": "object"})


@pytest.fixture(autouse=True)
def _fast_retries(settings):
    settings.GATEWAY_RETRY_DELAYS = (0, 0, 0)


@pytest.fixture
def ctx(organization, project) -> CallContext:
    return CallContext(organization_id=organization.id, project_id=project.id)


def profile(organization, name, provider="fake", model="fake-model", **kwargs) -> ModelProfile:
    return ModelProfile.objects.create(
        organization=organization, profile=name, provider=provider, model=model, **kwargs
    )


class Scripted:
    """Builder returning one scripted FakeProvider per resolved provider name."""

    def __init__(self, **scripts: list[FakeResponse]) -> None:
        self.providers = {name: FakeProvider(script) for name, script in scripts.items()}

    def __call__(self, resolved):
        return self.providers[resolved.provider]


def test_resolution_order(organization, project):
    assert resolve_profile(organization.id, project.id, "strong").source == "default"
    assert resolve_profile(organization.id, project.id, "strong").provider == "anthropic"
    profile(organization, "strong", provider="ollama", model="qwen3:14b")
    assert resolve_profile(organization.id, project.id, "strong").source == "organization"
    profile(organization, "strong", provider="openai", model="gpt-5", project=project)
    resolved = resolve_profile(organization.id, project.id, "strong")
    assert (resolved.source, resolved.provider) == ("project", "openai")
    assert resolve_profile(organization.id, None, "strong").provider == "ollama"
    with pytest.raises(ProfileConfigurationError):
        resolve_profile(organization.id, project.id, "embed")
    assert downgrade_chain("strong", True) == ["strong", "balanced", "fast"]
    assert downgrade_chain("strong", False) == ["strong"]


def test_api_key_comes_from_the_named_env_var(organization, monkeypatch):
    env_name = "MY_OPENAI_KEY"
    profile(organization, "fast", provider="openai", model="gpt-5", api_key_env=env_name)
    monkeypatch.setenv(env_name, "sk-from-env")  # pragma: allowlist secret
    config = resolve_profile(organization.id, None, "fast").config()
    assert config.api_key == "sk-from-env"  # pragma: allowlist secret


def test_cli_is_opt_in(organization):
    with pytest.raises(ValidationError, match="opt-in"):
        profile(organization, "strong", provider="anthropic-cli", model="claude-opus-5-5")
    with pytest.raises(ValidationError, match="no embeddings"):
        profile(
            organization,
            "embed",
            provider="anthropic-cli",
            model="x",
            options={"acknowledge_cli_terms": True},
        )
    row = profile(
        organization,
        "strong",
        provider="anthropic-cli",
        model="claude-opus-5-5",
        options={"acknowledge_cli_terms": True},
    )
    assert "anthropic-cli" in str(row)


def test_generate_records_the_call(organization, ctx):
    profile(organization, "balanced")
    out = generate(messages=MESSAGES, profile="balanced", max_tokens=50, ctx=ctx)
    assert out.result.message.text() == "fake: hi"
    assert out.call.status == CallStatus.OK
    assert out.profile.source == "organization"
    assert not out.downgraded


def test_data_residency_local_blocks_cloud_before_calling(organization, ctx):
    local = CallContext(
        organization_id=ctx.organization_id, project_id=ctx.project_id, data_residency="local"
    )
    with pytest.raises(ProfileConfigurationError, match="data_residency is local"):
        generate(messages=MESSAGES, profile="strong", max_tokens=50, ctx=local)  # anthropic default
    profile(organization, "fast", provider="openai-compatible", model="m", is_local=True)
    generate(
        messages=MESSAGES,
        profile="fast",
        max_tokens=50,
        ctx=local,
        builder=Scripted(**{"openai-compatible": [FakeResponse(text="ok")]}),
    )
    assert LLMCall.objects.count() == 1


def test_tool_use_must_be_supported(organization, ctx):
    profile(organization, "fast", provider="ollama", model="tiny", options={"tools": False})
    with pytest.raises(ProfileConfigurationError, match="no tool use"):
        generate(messages=MESSAGES, tools=[TOOL], profile="fast", max_tokens=50, ctx=ctx)


def test_retries_then_succeeds(organization, ctx):
    profile(organization, "balanced")
    builder = Scripted(
        fake=[FakeResponse(error="error"), FakeResponse(error="timeout"), FakeResponse(text="ok")]
    )
    out = generate(messages=MESSAGES, profile="balanced", max_tokens=50, ctx=ctx, builder=builder)
    assert out.result.message.text() == "ok"
    statuses = sorted(LLMCall.objects.values_list("status", flat=True))
    assert statuses == ["error", "ok", "timeout"]
    degraded = Event.objects.filter(type="provider.degraded")
    assert [e.payload["action"] for e in degraded] == ["retry"]


def test_rate_limit_waits_retry_after(organization, ctx, monkeypatch):
    profile(organization, "balanced")
    waits: list[float] = []
    monkeypatch.setattr(gateway, "_sleep", waits.append)
    builder = Scripted(fake=[FakeResponse(error="rate_limited"), FakeResponse(text="ok")])
    generate(messages=MESSAGES, profile="balanced", max_tokens=50, ctx=ctx, builder=builder)
    assert len(waits) == 1


def test_non_retryable_error_is_raised_at_once(organization, ctx):
    profile(organization, "balanced")
    builder = Scripted(fake=[FakeResponse(error="error", error_code="context_length")])
    with pytest.raises(Exception, match="fake error") as info:
        generate(messages=MESSAGES, profile="balanced", max_tokens=50, ctx=ctx, builder=builder)
    assert info.value.code == "context_length"
    assert LLMCall.objects.count() == 1


def test_downgrade_after_retries_are_exhausted(organization, ctx):
    profile(organization, "strong", provider="anthropic", model="claude-opus-5-5")
    profile(organization, "balanced", provider="openai", model="gpt-5")
    builder = Scripted(
        anthropic=[FakeResponse(error="error")] * 4, openai=[FakeResponse(text="from balanced")]
    )
    allow = CallContext(
        organization_id=ctx.organization_id, project_id=ctx.project_id, allow_downgrade=True
    )
    out = generate(messages=MESSAGES, profile="strong", max_tokens=50, ctx=allow, builder=builder)
    assert out.downgraded
    assert out.profile.profile == "balanced"
    assert out.result.message.text() == "from balanced"
    actions = [e.payload["action"] for e in Event.objects.filter(type="provider.degraded")]
    assert actions == ["retry", "downgrade"]


def test_open_breaker_fails_fast_or_downgrades(organization, ctx):
    profile(organization, "strong", provider="anthropic", model="claude-opus-5-5")
    profile(organization, "balanced", provider="openai", model="gpt-5")
    breaker = CircuitBreaker("anthropic")
    for _ in range(FAILURES):
        breaker.record_failure()
    assert breaker.state() == "open"
    builder = Scripted(anthropic=[], openai=[FakeResponse(text="ok")])
    with pytest.raises(ProviderUnavailableError):
        generate(messages=MESSAGES, profile="strong", max_tokens=50, ctx=ctx, builder=builder)
    assert LLMCall.objects.count() == 0
    allow = CallContext(
        organization_id=ctx.organization_id, project_id=ctx.project_id, allow_downgrade=True
    )
    out = generate(messages=MESSAGES, profile="strong", max_tokens=50, ctx=allow, builder=builder)
    assert out.profile.provider == "openai"
    actions = [e.payload["action"] for e in Event.objects.filter(type="provider.degraded")]
    assert actions == ["wait", "downgrade"]


def test_idempotency_key_reuses_the_stored_response(organization, ctx):
    profile(organization, "balanced")
    builder = Scripted(fake=[FakeResponse(text="first"), FakeResponse(text="second")])
    kwargs = {
        "messages": MESSAGES,
        "profile": "balanced",
        "max_tokens": 50,
        "ctx": ctx,
        "builder": builder,
    }
    one = generate(**kwargs, idempotency_key="turn:llm:1")
    two = generate(**kwargs, idempotency_key="turn:llm:1")
    assert one.call.id == two.call.id
    assert two.result.message.text() == "first"
    assert generate(**kwargs, idempotency_key="turn:llm:2").result.message.text() == "second"


def test_breaker_states():
    now = [1000.0]
    breaker = CircuitBreaker("unit-test", clock=lambda: now[0])
    breaker.record_success()
    assert breaker.allow()
    for _ in range(FAILURES - 1):
        assert not breaker.record_failure()
    assert breaker.record_failure()
    assert breaker.state() == "open"
    assert not breaker.allow()
    now[0] += OPEN_S + 1
    assert breaker.state() == "half_open"
    assert breaker.allow()  # the single probe
    assert not breaker.allow()
    assert breaker.record_failure()  # probe failed: open again
    assert breaker.state() == "open"
    now[0] += OPEN_S + 1
    assert breaker.allow()
    assert breaker.record_success()  # recovered
    assert breaker.state() == "closed"


def test_recovered_event_after_half_open_success(organization, ctx):
    profile(organization, "balanced")
    breaker = CircuitBreaker("fake")
    for _ in range(FAILURES):
        breaker.record_failure()
    breaker.client.set(breaker.open_key, "0")  # expired: half-open
    generate(messages=MESSAGES, profile="balanced", max_tokens=50, ctx=ctx)
    assert Event.objects.filter(type="provider.recovered").count() == 1
