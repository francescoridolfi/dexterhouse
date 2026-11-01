# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run one completion through one provider and record the `LLMCall` with its EUR cost."""

import time
import uuid
from collections.abc import Callable, Iterator
from decimal import Decimal

import structlog

from dexterhouse.apps.gateway.messages import (
    CompletionRequest,
    CompletionResult,
    StreamEvent,
    Usage,
)
from dexterhouse.apps.gateway.models import CallStatus, LLMCall
from dexterhouse.apps.gateway.pricing import QUANTUM, get_prices
from dexterhouse.apps.gateway.providers import Provider, ProviderError, collect
from dexterhouse.apps.observability import tracing
from dexterhouse.apps.observability.services import budget

logger = structlog.get_logger(__name__)

CLI_PRICE_VERSION = "cli"
StreamCallback = Callable[[StreamEvent], None]


def complete(
    request: CompletionRequest,
    *,
    provider: Provider,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    agent_turn_id: uuid.UUID | None = None,
    trace_id: str = "",
    idempotency_key: str = "",
    on_event: StreamCallback | None = None,
) -> tuple[CompletionResult, LLMCall]:
    """Call `provider`, aggregate the stream and persist one `LLMCall` (also on failure).

    With an `idempotency_key`, a successful call already recorded under that key is returned
    from its stored response without calling the provider again (ADR-0013: a resumed turn
    never pays twice). `on_event` sees every streaming event (used for `agent.speaking`).

    Raises:
        BudgetExceededError: the project or organization budget is exhausted (F-012); no
            provider call and no `LLMCall` are made.
    """
    if idempotency_key:
        done = LLMCall.objects.filter(
            idempotency_key=idempotency_key, status=CallStatus.OK, response__isnull=False
        ).first()
        if done is not None:
            return CompletionResult.model_validate(done.response), done
    budget.check_before_call(organization_id, project_id)
    with tracing.span("llm.call", provider=provider.name, model=request.model):
        result, call = _call(
            request,
            provider,
            organization_id,
            project_id,
            agent_turn_id,
            trace_id,
            idempotency_key,
            on_event,
        )
    budget.record_spend(organization_id, project_id)
    return result, call


def _call(
    request: CompletionRequest,
    provider: Provider,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    agent_turn_id: uuid.UUID | None,
    trace_id: str,
    idempotency_key: str,
    on_event: StreamCallback | None,
) -> tuple[CompletionResult, LLMCall]:
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
        events = _tee(provider.stream(request), on_event)
        result = collect(events, provider=provider.name, model=request.model)
    except ProviderError as exc:
        call.status = exc.status
        call.error_detail = f"{exc.code}: {exc}"
        call.latency_ms = _elapsed_ms(started)
        call.save()
        logger.warning(
            "gateway.call_failed", provider=call.provider, model=call.model, status=call.status
        )
        raise
    call.latency_ms = _elapsed_ms(started)
    call.status = CallStatus.OK
    call.idempotency_key = idempotency_key
    call.response = result.model_dump(mode="json")
    _apply_usage(call, result.usage)
    call.save()
    logger.info(
        "gateway.call_completed",
        provider=call.provider,
        model=call.model,
        latency_ms=call.latency_ms,
        input_tokens=call.input_tokens,
        output_tokens=call.output_tokens,
        cost=str(call.cost) if call.cost is not None else None,
    )
    return result, call


def _tee(events: Iterator[StreamEvent], on_event: StreamCallback | None) -> Iterator[StreamEvent]:
    for event in events:
        if on_event is not None:
            on_event(event)
        yield event


def _apply_usage(call: LLMCall, usage: Usage) -> None:
    prices = get_prices()
    call.input_tokens = usage.input
    call.output_tokens = usage.output
    call.cached_tokens = usage.cached_read
    call.cache_write_tokens = usage.cached_write
    if usage.cost_usd is not None:
        # The CLI reports its own cost (CD-024): convert once, mark the price version.
        call.cost = (Decimal(str(usage.cost_usd)) * prices.eur_per_usd).quantize(QUANTUM)
        call.price_version = CLI_PRICE_VERSION
        return
    call.cost = prices.cost_eur(call.provider, call.model, usage)
    call.price_version = prices.price_version
    if call.cost is None:
        logger.warning("gateway.pricing_missing", provider=call.provider, model=call.model)


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
