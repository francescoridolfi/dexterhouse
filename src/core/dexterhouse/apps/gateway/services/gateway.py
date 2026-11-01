# SPDX-License-Identifier: AGPL-3.0-or-later
"""`generate()`: the gateway entry point used by the agents runtime.

Profile resolution, `data_residency` and tool-use checks, circuit breaker, retry with
backoff (408/5xx/connection: 2, 4, 8 s + jitter; 429: `retry-after` up to 60 s), optional
downgrade `strong → balanced → fast`, `provider.*` events, one `LLMCall` per attempt.
"""

import random
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import structlog
from django.conf import settings

from dexterhouse.apps.events.schemas import Actor
from dexterhouse.apps.events.services.publisher import emit
from dexterhouse.apps.gateway.messages import (
    CompletionRequest,
    CompletionResult,
    Message,
    ToolSpec,
)
from dexterhouse.apps.gateway.models import LLMCall
from dexterhouse.apps.gateway.providers import Provider, ProviderError, get_provider
from dexterhouse.apps.gateway.services.complete import StreamCallback, complete
from dexterhouse.apps.gateway.services.profiles import (
    DataResidency,
    ResolvedProfile,
    check_profile,
    downgrade_chain,
    resolve_profile,
)
from dexterhouse.apps.gateway.services.resilience import CircuitBreaker

logger = structlog.get_logger(__name__)

DEFAULT_RETRY_DELAYS = (2.0, 4.0, 8.0)
SYSTEM = Actor(type="system", name="gateway")
_REASONS = {"rate_limited": "rate_limit", "timeout": "timeout"}

#: Patched by tests to inject providers built on recorded responses.
ProviderBuilder = Callable[[ResolvedProfile], Provider]


def default_builder(resolved: ResolvedProfile) -> Provider:
    return get_provider(resolved.provider, resolved.config())


class ProviderUnavailableError(ProviderError):
    """Breaker open (and no downgrade): the caller waits and retries later."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="unavailable", retryable=True)


@dataclass(frozen=True)
class CallContext:
    """Who pays and what is allowed: comes from the project and the agent."""

    organization_id: uuid.UUID
    project_id: uuid.UUID
    agent_turn_id: uuid.UUID | None = None
    trace_id: str = ""
    data_residency: DataResidency = "any"
    allow_downgrade: bool = False


@dataclass(frozen=True)
class GatewayResult:
    result: CompletionResult
    call: LLMCall
    profile: ResolvedProfile
    downgraded: bool = False


def generate(
    *,
    messages: list[Message],
    profile: str,
    max_tokens: int,
    ctx: CallContext,
    tools: list[ToolSpec] | None = None,
    temperature: float | None = None,
    idempotency_key: str = "",
    on_event: StreamCallback | None = None,
    builder: ProviderBuilder | None = None,
) -> GatewayResult:
    """Complete `messages` with the model mapped to `profile`.

    Raises:
        ProfileConfigurationError: residency, tool-use or opt-in check failed (no call made).
        ProviderUnavailableError: every profile in the chain has its breaker open.
        ProviderError: a non-retryable error, or retries exhausted without downgrade.
    """
    builder = builder or default_builder
    tools = tools or []
    chain = downgrade_chain(profile, ctx.allow_downgrade)
    last_error: ProviderError | None = None
    for index, name in enumerate(chain):
        resolved = resolve_profile(ctx.organization_id, ctx.project_id, name)
        check_profile(resolved, data_residency=ctx.data_residency, needs_tools=bool(tools))
        has_next = index + 1 < len(chain)
        breaker = CircuitBreaker(resolved.provider)
        if not breaker.allow():
            _degraded(ctx, resolved, "error", "downgrade" if has_next else "wait")
            last_error = ProviderUnavailableError(f"{resolved.provider} circuit breaker is open")
            continue
        request = CompletionRequest(
            messages=messages,
            tools=tools,
            profile=name,  # type: ignore[arg-type]
            model=resolved.model,
            max_tokens=min(max_tokens, int(resolved.options.get("max_tokens") or max_tokens)),
            temperature=_temperature(resolved, temperature),
            metadata={
                "project_id": str(ctx.project_id),
                "agent_turn_id": str(ctx.agent_turn_id or ""),
                "trace_id": ctx.trace_id,
            },
        )
        try:
            result, call = _with_retries(
                request, builder(resolved), ctx, resolved, breaker, idempotency_key, on_event
            )
        except ProviderError as exc:
            if not exc.retryable or not has_next:
                raise
            _degraded(ctx, resolved, _REASONS.get(exc.status, "error"), "downgrade")
            last_error = exc
            continue
        return GatewayResult(result=result, call=call, profile=resolved, downgraded=index > 0)
    raise last_error or ProviderUnavailableError("no profile available")


def _with_retries(
    request: CompletionRequest,
    provider: Provider,
    ctx: CallContext,
    resolved: ResolvedProfile,
    breaker: CircuitBreaker,
    idempotency_key: str,
    on_event: StreamCallback | None,
) -> tuple[CompletionResult, LLMCall]:
    delays = tuple(getattr(settings, "GATEWAY_RETRY_DELAYS", DEFAULT_RETRY_DELAYS))
    for attempt in range(len(delays) + 1):
        try:
            result, call = complete(
                request,
                provider=provider,
                organization_id=ctx.organization_id,
                project_id=ctx.project_id,
                agent_turn_id=ctx.agent_turn_id,
                trace_id=ctx.trace_id,
                idempotency_key=idempotency_key,
                on_event=on_event,
            )
        except ProviderError as exc:
            if not exc.retryable:
                raise
            if breaker.record_failure() or attempt == len(delays):
                raise
            if attempt == 0:
                _degraded(ctx, resolved, _REASONS.get(exc.status, "error"), "retry")
            _sleep(_delay(exc, delays[attempt]))
            continue
        if breaker.record_success():
            _recovered(ctx, resolved)
        return result, call
    raise AssertionError("unreachable")  # pragma: no cover


def _delay(exc: ProviderError, base: float) -> float:
    if exc.status == "rate_limited" and exc.retry_after is not None:
        return exc.retry_after
    jitter = random.uniform(0, base / 4)  # noqa: S311 # nosec B311: backoff jitter, not crypto
    return base + jitter if base else 0.0


def _sleep(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def _temperature(resolved: ResolvedProfile, requested: float | None) -> float:
    if requested is not None:
        return requested
    return float(resolved.options.get("temperature", 0.2))


def _degraded(ctx: CallContext, resolved: ResolvedProfile, reason: str, action: str) -> None:
    logger.warning("gateway.provider_degraded", provider=resolved.provider, action=action)
    _emit(
        "provider.degraded",
        ctx,
        {
            "provider": resolved.provider,
            "reason": reason,
            "action": action,
            "profile": resolved.profile,
        },
    )


def _recovered(ctx: CallContext, resolved: ResolvedProfile) -> None:
    _emit("provider.recovered", ctx, {"provider": resolved.provider})


def _emit(event_type: str, ctx: CallContext, payload: dict[str, Any]) -> None:
    emit(
        event_type,
        organization_id=ctx.organization_id,
        project_id=ctx.project_id,
        actor=SYSTEM,
        payload=payload,
        correlation_id=ctx.agent_turn_id,
    )
