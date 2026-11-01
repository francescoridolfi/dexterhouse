# SPDX-License-Identifier: AGPL-3.0-or-later
"""Circuit breaker per provider, shared by every worker through Redis (llm_gateway_detail.md).

5 failures within 60 s open the breaker for 120 s; then one probe request is let through
(half-open): success closes it, failure opens it again.
"""

import time
import uuid
from collections.abc import Callable
from typing import Literal

import redis
import structlog

from dexterhouse.apps.events.services.streams import get_client

logger = structlog.get_logger(__name__)

FAILURES = 5
WINDOW_S = 60
OPEN_S = 120
State = Literal["closed", "open", "half_open"]


class CircuitBreaker:
    def __init__(
        self,
        provider: str,
        client: redis.Redis | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.provider = provider
        self.client = client or get_client()
        self.clock = clock
        prefix = f"dh:gateway:breaker:{provider}"
        self.fails_key = f"{prefix}:fails"
        self.open_key = f"{prefix}:open_until"
        self.probe_key = f"{prefix}:probe"

    def state(self) -> State:
        try:
            raw = self.client.get(self.open_key)
        except redis.RedisError:
            return "closed"  # fail open: Redis trouble must not stop every LLM call
        if raw is None:
            return "closed"
        return "open" if self.clock() < float(raw) else "half_open"

    def allow(self) -> bool:
        """Whether a request may go to the provider now (claims the probe when half-open)."""
        state = self.state()
        if state == "closed":
            return True
        if state == "open":
            return False
        try:
            return bool(self.client.set(self.probe_key, "1", nx=True, ex=OPEN_S))
        except redis.RedisError:
            return True

    def record_failure(self) -> bool:
        """Count a failure; True when this failure opened the breaker."""
        now = self.clock()
        try:
            if self.state() == "half_open":
                self._open(now)
                return True
            pipe = self.client.pipeline()
            pipe.zadd(self.fails_key, {f"{now}:{uuid.uuid4().hex}": now})  # unique per failure
            pipe.zremrangebyscore(self.fails_key, 0, now - WINDOW_S)
            pipe.zcard(self.fails_key)
            pipe.expire(self.fails_key, WINDOW_S)
            count = pipe.execute()[2]
            if count >= FAILURES:
                self._open(now)
                return True
        except redis.RedisError as exc:
            logger.warning("gateway.breaker_unavailable", provider=self.provider, error=str(exc))
        return False

    def record_success(self) -> bool:
        """Close the breaker; True when it was open or half-open (provider recovered)."""
        try:
            was_open = self.client.delete(self.open_key) > 0
            self.client.delete(self.fails_key, self.probe_key)
        except redis.RedisError:
            return False
        return was_open

    def _open(self, now: float) -> None:
        pipe = self.client.pipeline()
        pipe.set(self.open_key, f"{now + OPEN_S}", ex=OPEN_S * 10)
        pipe.delete(self.fails_key, self.probe_key)
        pipe.execute()
        logger.warning("gateway.breaker_open", provider=self.provider, seconds=OPEN_S)
