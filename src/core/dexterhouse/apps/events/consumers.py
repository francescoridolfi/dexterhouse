# SPDX-License-Identifier: AGPL-3.0-or-later
"""`/ws/projects/{id}`: snapshot, live events from Redis Streams, resync (contracts/api)."""

import asyncio
import contextlib
import uuid
from collections import deque
from typing import Any

import redis
import structlog
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.utils import timezone

from dexterhouse.apps.events.schemas import EventEnvelope
from dexterhouse.apps.events.services import limits, replay, streams

logger = structlog.get_logger(__name__)

HEARTBEAT_S = 25.0
READ_BLOCK_MS = 5_000
SEEN_IDS = 5_000
CLOSE_CODES = {
    "unauthorized": 4401,
    "forbidden": 4403,
    "not_found": 4404,
    "rate_limited": 4429,
}
SPEAKING = "agent.speaking"


class ProjectEventsConsumer(AsyncJsonWebsocketConsumer):
    """One connection per project per client (4429 beyond); unknown messages are ignored."""

    heartbeat_s = HEARTBEAT_S

    async def connect(self) -> None:
        self.project_id = uuid.UUID(self.scope["url_route"]["kwargs"]["project_id"])
        self.speaking_enabled = True
        self.seen: deque[str] = deque(maxlen=SEEN_IDS)
        self.tasks: list[asyncio.Task[None]] = []
        self.slot: limits.ConnectionSlot | None = None
        self.rate = limits.MessageRate()
        await self.accept()
        verdict = await database_sync_to_async(replay.access)(
            self.scope.get("user"), self.scope.get("api_token"), self.project_id
        )
        if verdict != "ok":
            code = "not_found" if verdict == "not_found" else "forbidden"
            await self.send_json({"type": "error", "code": code, "detail": verdict})
            await self.close(code=CLOSE_CODES[verdict])
            return
        self.redis = streams.get_async_client()
        self.slot = limits.ConnectionSlot(
            self.redis,
            str(self.project_id),
            limits.client_id(self.scope),
            settings.WS_CONNECTIONS_PER_PROJECT,
        )
        if not await self.slot.claim():
            await self._refuse("too many connections to this project from this client")
            return
        start_id = await self._latest_stream_id()
        await self.send_json(await database_sync_to_async(replay.snapshot)(self.project_id))
        self.tasks = [
            asyncio.create_task(self._forward(start_id)),
            asyncio.create_task(self._heartbeat()),
        ]

    async def disconnect(self, code: int) -> None:
        for task in self.tasks:
            task.cancel()
        for task in self.tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if getattr(self, "slot", None) is not None:
            with contextlib.suppress(redis.RedisError):
                await self.slot.release()
        if hasattr(self, "redis"):
            await self.redis.aclose()

    async def _refuse(self, detail: str) -> None:
        await self.send_json({"type": "error", "code": "rate_limited", "detail": detail})
        await self.close(code=CLOSE_CODES["rate_limited"])

    async def receive_json(self, content: Any, **kwargs: Any) -> None:
        if not self.rate.allow():
            await self._refuse("too many messages")
            return
        kind = content.get("type") if isinstance(content, dict) else None
        if kind == "ping":
            await self._send_heartbeat()
        elif kind == "subscribe_speaking":
            self.speaking_enabled = bool(content.get("enabled", True))
        elif kind == "resync":
            await self._resync(content.get("since_event_id"))

    async def _latest_stream_id(self) -> str:
        entries = await self.redis.xrevrange(streams.stream_key(self.project_id), count=1)
        if not entries:
            return "0-0"
        entry_id = entries[0][0]
        return entry_id.decode() if isinstance(entry_id, bytes) else entry_id

    async def _forward(self, last_id: str) -> None:
        key = streams.stream_key(self.project_id)
        while True:
            try:
                response = await self.redis.xread({key: last_id}, block=READ_BLOCK_MS, count=100)
            except redis.RedisError as exc:
                logger.warning("events.ws_read_failed", error=str(exc))
                await asyncio.sleep(1)
                continue
            for _key, entries in response or []:
                for entry_id, fields in entries:
                    last_id = entry_id.decode() if isinstance(entry_id, bytes) else entry_id
                    await self._send_envelope(streams.decode(fields))

    async def _send_envelope(self, envelope: EventEnvelope) -> None:
        if envelope.type == SPEAKING:
            if self.speaking_enabled:
                await self.send_json({"type": "speaking", **envelope.payload})
            return
        event_id = str(envelope.id)
        if event_id in self.seen:
            return
        self.seen.append(event_id)
        await self.send_json({"type": "event", "event": envelope.model_dump(mode="json")})

    async def _resync(self, since_event_id: Any) -> None:
        try:
            since = uuid.UUID(str(since_event_id))
        except ValueError:
            since = None
        missing = (
            await database_sync_to_async(replay.events_since)(self.project_id, since)
            if since
            else None
        )
        if missing is None:
            await self.send_json(await database_sync_to_async(replay.snapshot)(self.project_id))
            return
        for envelope in missing:
            await self._send_envelope(envelope)

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_s)
            await self._send_heartbeat()
            if self.slot is not None:
                with contextlib.suppress(redis.RedisError):
                    await self.slot.refresh()

    async def _send_heartbeat(self) -> None:
        await self.send_json({"type": "heartbeat", "server_time": timezone.now().isoformat()})
