# SPDX-License-Identifier: AGPL-3.0-or-later
"""WebSocket limits (T16, ST-21): connections per project per client, client message rate.

A client is an API token, else a browser session, else a user. Each open connection holds a
slot in a Redis sorted set scored by its last heartbeat, so slots of crashed workers expire
after `STALE_S` instead of locking the client out.
"""

import time
import uuid
from collections import deque
from typing import Any

from redis import asyncio as aioredis

STALE_S = 90  # three heartbeats
MESSAGES = 20  # client messages per window
WINDOW_S = 10.0

_CLAIM = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', tonumber(ARGV[1]) - tonumber(ARGV[2]))
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[3]) then return 0 end
redis.call('ZADD', KEYS[1], ARGV[1], ARGV[4])
redis.call('EXPIRE', KEYS[1], ARGV[2])
return 1
"""


def client_id(scope: dict[str, Any]) -> str:
    """The identity a connection limit applies to."""
    token = scope.get("api_token")
    if token is not None:
        return f"token:{token.pk}"
    session = scope.get("session")
    key = getattr(session, "session_key", None)
    if key:
        return f"session:{key}"
    user = scope.get("user")
    return f"user:{getattr(user, 'pk', None)}"


class ConnectionSlot:
    """One connection's slot in `dh:ws:conn:<channel>:<client>`."""

    def __init__(self, redis: aioredis.Redis, channel: str, client: str, limit: int) -> None:
        self.redis = redis
        self.key = f"dh:ws:conn:{channel}:{client}"
        self.member = uuid.uuid4().hex
        self.limit = limit
        self.held = False

    async def claim(self) -> bool:
        claimed = await self.redis.eval(
            _CLAIM, 1, self.key, time.time(), STALE_S, self.limit, self.member
        )
        self.held = bool(claimed)
        return self.held

    async def refresh(self) -> None:
        if self.held:
            await self.redis.zadd(self.key, {self.member: time.time()}, xx=True)
            await self.redis.expire(self.key, STALE_S)

    async def release(self) -> None:
        if self.held:
            await self.redis.zrem(self.key, self.member)
            self.held = False


class MessageRate:
    """Sliding window of client messages; `allow()` is False once the window is full."""

    def __init__(self, limit: int | None = None, window_s: float | None = None) -> None:
        self.limit = MESSAGES if limit is None else limit
        self.window_s = WINDOW_S if window_s is None else window_s
        self.seen: deque[float] = deque()

    def allow(self) -> bool:
        now = time.monotonic()
        while self.seen and now - self.seen[0] > self.window_s:
            self.seen.popleft()
        if len(self.seen) >= self.limit:
            return False
        self.seen.append(now)
        return True
