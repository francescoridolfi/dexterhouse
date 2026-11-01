# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run a completion through a provider and record the `LLMCall` with its EUR cost."""

import time
import uuid

import structlog

from dexterhouse.apps.gateway.messages import CompletionRequest, CompletionResult, Usage
from dexterhouse.apps.gateway.models import CallStatus, LLMCall
from dexterhouse.apps.gateway.pricing import get_prices
from dexterhouse.apps.gateway.providers import Provider, ProviderError, collect

logger = structlog.get_logger(__name__)


def complete(
    request: CompletionRequest,
    *,
    provider: Provider,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    agent_turn_id: uuid.UUID | None = None,
    trace_id: str = "",
) -> tuple[CompletionResult, LLMCall]:
    """Call `provider`, aggregate the stream and persist one `LLMCall` (also on failure).

    Budget checks and `Project.spent` updates arrive with the projects app; models missing
    from the price table get `cost = null` and a `pricing_missing` warning.
    """
    started = time.monotonic()
    call = LLMCall(
        organization_id=organization_id,
        project_id=project_id,
        agent_turn_id=agent_turn_id,
        provider=provider.name,
        model=request.model,
        profile=request.profile,
        trace_id=trace_id,
    )
    try:
        result = collect(provider.stream(request), provider=provider.name, model=request.model)
    except ProviderError as exc:
        call.status = exc.status
        call.error_detail = str(exc)
        call.latency_ms = _elapsed_ms(started)
        call.save()
        raise
    call.latency_ms = _elapsed_ms(started)
    call.status = CallStatus.OK
    _apply_usage(call, result.usage)
    call.save()
    return result, call


def _apply_usage(call: LLMCall, usage: Usage) -> None:
    prices = get_prices()
    call.input_tokens = usage.input
    call.output_tokens = usage.output
    call.cached_tokens = usage.cached_read
    call.cache_write_tokens = usage.cached_write
    call.cost = prices.cost_eur(call.provider, call.model, usage)
    call.price_version = prices.price_version
    if call.cost is None:
        logger.warning("gateway.pricing_missing", provider=call.provider, model=call.model)


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
