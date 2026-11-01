# SPDX-License-Identifier: AGPL-3.0-or-later
import asyncio
import uuid

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator

from dexterhouse.apps.accounts.services.tokens import create_token
from dexterhouse.apps.events.consumers import ProjectEventsConsumer
from dexterhouse.apps.events.schemas import Actor
from dexterhouse.apps.events.services import publisher, replay
from dexterhouse.asgi import websocket_application

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def token(organization, user) -> str:
    return create_token(organization=organization, user=user, name="ws", scopes=["events:read"])[1]


def emit(organization, project_id, phase_id="analysis"):
    return publisher.emit(
        "phase.ready",
        organization_id=organization.id,
        project_id=project_id,
        actor=Actor(type="system"),
        payload={"phase_id": phase_id},
    )


async def connect(project_id, token: str | None = None) -> WebsocketCommunicator:
    path = f"/ws/projects/{project_id}" + (f"?token={token}" if token else "")
    communicator = WebsocketCommunicator(websocket_application, path)
    connected, _ = await communicator.connect()
    assert connected
    return communicator


async def test_rejects_anonymous(project_id):
    communicator = await connect(project_id)
    assert (await communicator.receive_json_from())["code"] == "forbidden"
    assert (await communicator.receive_output())["code"] == 4401


async def test_rejects_token_without_scope(organization, user, project_id):
    _, plaintext = await database_sync_to_async(create_token)(
        organization=organization, user=user, name="ro", scopes=["projects:read"]
    )
    communicator = await connect(project_id, plaintext)
    assert (await communicator.receive_json_from())["type"] == "error"


async def test_snapshot_live_events_speaking_and_ping(organization, project_id, token):
    first = await database_sync_to_async(emit)(organization, project_id)
    communicator = await connect(project_id, token)
    snapshot = await communicator.receive_json_from()
    assert snapshot["type"] == "snapshot"
    assert snapshot["last_event_id"] == str(first.id)

    second = await database_sync_to_async(emit)(organization, project_id, "design")
    message = await communicator.receive_json_from(timeout=5)
    assert message["type"] == "event"
    assert message["event"]["id"] == str(second.id)
    assert message["event"]["payload"] == {"phase_id": "design"}

    speaking = {"turn_id": str(uuid.uuid4()), "agent_id": str(uuid.uuid4()), "text": "hm", "seq": 3}
    await database_sync_to_async(publisher.emit)(
        "agent.speaking",
        organization_id=organization.id,
        project_id=project_id,
        actor=Actor(type="agent"),
        payload=speaking,
    )
    assert await communicator.receive_json_from(timeout=5) == {"type": "speaking", **speaking}

    await communicator.send_json_to({"type": "subscribe_speaking", "enabled": False})
    await communicator.send_json_to({"type": "ping"})
    assert (await communicator.receive_json_from())["type"] == "heartbeat"
    await communicator.disconnect()


async def test_resync_replays_missing_events_once(organization, project_id, token):
    first = await database_sync_to_async(emit)(organization, project_id)
    second = await database_sync_to_async(emit)(organization, project_id, "design")
    communicator = await connect(project_id, token)
    await communicator.receive_json_from()  # snapshot
    await communicator.send_json_to({"type": "resync", "since_event_id": str(first.id)})
    message = await communicator.receive_json_from(timeout=5)
    assert message["event"]["id"] == str(second.id)
    await communicator.send_json_to({"type": "resync", "since_event_id": str(first.id)})
    await communicator.send_json_to({"type": "ping"})
    assert (await communicator.receive_json_from())["type"] == "heartbeat"  # duplicate skipped
    await communicator.disconnect()


@pytest.mark.parametrize("since", ["not-a-uuid", str(uuid.uuid4())])
async def test_resync_unknown_anchor_sends_snapshot(project_id, token, since):
    communicator = await connect(project_id, token)
    await communicator.receive_json_from()
    await communicator.send_json_to({"type": "resync", "since_event_id": since})
    assert (await communicator.receive_json_from())["type"] == "snapshot"
    await communicator.send_json_to(["ignored"])
    await communicator.disconnect()


async def test_heartbeat_is_periodic(project_id, token, monkeypatch):
    monkeypatch.setattr(ProjectEventsConsumer, "heartbeat_s", 0.05)
    communicator = await connect(project_id, token)
    await communicator.receive_json_from()
    assert (await communicator.receive_json_from(timeout=2))["type"] == "heartbeat"
    await communicator.disconnect()
    await asyncio.sleep(0)


def test_session_user_needs_membership(user, django_user_model):
    outsider = django_user_model.objects.create_user(username="eve")
    assert replay.can_read_events(user, None) is True
    assert replay.can_read_events(outsider, None) is False
    assert replay.can_read_events(None, None) is False


def test_resync_limit_requests_snapshot(organization, project_id, monkeypatch):
    first = emit(organization, project_id)
    emit(organization, project_id, "a")
    emit(organization, project_id, "b")
    monkeypatch.setattr(replay, "RESYNC_LIMIT", 1)
    assert replay.events_since(project_id, first.id) is None
