# SPDX-License-Identifier: AGPL-3.0-or-later
"""The same contract for every provider: streaming, normalised tool use, errors, costs."""

from decimal import Decimal

import pytest

from dexterhouse.apps.gateway.messages import (
    Stop,
    TextDelta,
    ToolCallDelta,
    ToolCallEnd,
    ToolCallPart,
    ToolCallStart,
    Usage,
)
from dexterhouse.apps.gateway.models import CallStatus, LLMCall
from dexterhouse.apps.gateway.providers import Provider, ProviderError, collect
from dexterhouse.apps.gateway.services.complete import complete

from .conftest import ALL_PROVIDERS, make_request, scenarios

STREAM_CASES = [(p, s) for p in ALL_PROVIDERS for s in ("text", "tool_use")]
ERROR_CASES = [(p, s) for p in ALL_PROVIDERS for s in scenarios(p, errors=True)]


@pytest.mark.parametrize(("provider", "scenario"), STREAM_CASES)
def test_stream_contract(build, provider, scenario):
    instance, _, cassette = build(provider, scenario)
    expect = cassette["expect"]
    assert isinstance(instance, Provider)
    events = list(instance.stream(make_request(cassette["model"])))

    # Shape: deltas and tool calls first, then exactly one Usage and one Stop, in that order.
    assert isinstance(events[-2], Usage)
    assert isinstance(events[-1], Stop)
    assert not any(isinstance(e, Usage | Stop) for e in events[:-2])
    open_ids: set[str] = set()
    for event in events[:-2]:
        if isinstance(event, ToolCallStart):
            assert event.id not in open_ids
            open_ids.add(event.id)
        elif isinstance(event, ToolCallDelta):
            assert event.id in open_ids
        elif isinstance(event, ToolCallEnd):
            open_ids.remove(event.id)
        else:
            assert isinstance(event, TextDelta)
    assert not open_ids

    result = collect(events, provider=provider, model=cassette["model"])
    assert result.message.text() == expect["text"]
    calls = [p for p in result.message.parts if isinstance(p, ToolCallPart)]
    assert [{"name": c.name, "args": c.args} for c in calls] == expect["tool_calls"]
    assert all(c.id for c in calls)
    assert result.stop_reason == expect["stop"]
    usage = result.usage.model_dump(exclude={"kind", "cost_usd"})
    assert usage == expect["usage"]


@pytest.mark.parametrize(("provider", "scenario"), ERROR_CASES)
def test_error_contract(build, provider, scenario):
    instance, _, cassette = build(provider, scenario)
    with pytest.raises(ProviderError) as info:
        list(instance.stream(make_request(cassette["model"])))
    error = info.value
    actual = {
        "status": error.status,
        "code": error.code,
        "retryable": error.retryable,
        "retry_after": error.retry_after,
    }
    assert actual == cassette["expect"]["error"]


@pytest.mark.django_db
@pytest.mark.parametrize("provider", ALL_PROVIDERS)
def test_cost_recorded(build, organization, provider):
    instance, _, cassette = build(provider, "text")
    project_id = organization.id  # any uuid: projects arrive with E-02
    result, call = complete(
        make_request(cassette["model"]),
        provider=instance,
        organization_id=organization.id,
        project_id=project_id,
        idempotency_key=f"contract:{provider}",
    )
    call.refresh_from_db()
    assert call.status == CallStatus.OK
    assert call.provider == provider
    assert call.cost == Decimal(cassette["expect"]["cost_eur"])
    assert call.price_version == cassette["expect"]["price_version"]
    assert call.input_tokens == cassette["expect"]["usage"]["input"]
    assert call.cached_tokens == cassette["expect"]["usage"]["cached_read"]
    # Same key again: served from the stored response, no second call or row.
    again, same = complete(
        make_request(cassette["model"]),
        provider=instance,
        organization_id=organization.id,
        project_id=project_id,
        idempotency_key=f"contract:{provider}",
    )
    assert same.id == call.id
    assert again == result
    assert LLMCall.objects.filter(provider=provider).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("provider", ALL_PROVIDERS)
def test_failed_call_is_recorded(build, organization, provider):
    scenario = "server_error"
    instance, _, cassette = build(provider, scenario)
    with pytest.raises(ProviderError):
        complete(
            make_request(cassette["model"]),
            provider=instance,
            organization_id=organization.id,
            project_id=organization.id,
        )
    call = LLMCall.objects.get(provider=provider)
    assert call.status == CallStatus.ERROR
    assert call.cost is None
    assert call.error_detail.startswith("provider:")
