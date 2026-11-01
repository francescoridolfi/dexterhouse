# SPDX-License-Identifier: AGPL-3.0-or-later
import asyncio
import uuid

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator

from dexterhouse.apps.accounts.models import Membership, Organization
from dexterhouse.apps.accounts.services.tokens import create_token, resolve_token
from dexterhouse.apps.events.auth import OriginValidatorAllowingNonBrowsers
from dexterhouse.apps.events.consumers import ProjectEventsConsumer
from dexterhouse.apps.events.schemas import Actor
from dexterhouse.apps.events.services import limits, publisher, replay, streams
from dexterhouse.apps.projects.services.projects import create_project
from dexterhouse.asgi import websocket_application

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def project_id(organization, user):
    """A real project (access is checked per project); its stream is deleted afterwards."""
    project = create_project(organization, user, {"name": "WS", "brief": "b", "budget": "1"})
    yield project.id
    streams.get_client().delete(streams.stream_key(project.id))


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
    assert snapshot["project"]["id"] == str(project_id)
    assert snapshot["project"]["status"] == "draft"
    assert snapshot["agents"] == []  # the team is hired when the process starts

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


def test_session_user_needs_membership_of_the_project_org(user, project_id, django_user_model):
    outsider = django_user_model.objects.create_user(username="eve")
    assert replay.access(user, None, project_id) == "ok"
    assert replay.access(outsider, None, project_id) == "forbidden"
    assert replay.access(None, None, project_id) == "unauthorized"
    assert replay.access(user, None, uuid.uuid4()) == "not_found"


def test_token_of_another_organization_is_forbidden(user, project_id):
    other = Organization.objects.create(slug="other", name="Other")
    Membership.objects.create(user=user, organization=other, role="owner")
    token, _ = create_token(organization=other, user=user, name="x", scopes=["events:read"])
    assert replay.access(user, token, project_id) == "forbidden"


async def test_unknown_project_closes_with_4404(token):
    communicator = await connect(uuid.uuid4(), token)
    assert (await communicator.receive_json_from())["code"] == "not_found"
    assert (await communicator.receive_output())["code"] == 4404


def test_resync_limit_requests_snapshot(organization, project_id, monkeypatch):
    first = emit(organization, project_id)
    emit(organization, project_id, "a")
    emit(organization, project_id, "b")
    monkeypatch.setattr(replay, "RESYNC_LIMIT", 1)
    assert replay.events_since(project_id, first.id) is None


@pytest.mark.parametrize(
    ("headers", "accepted"),
    [
        ([], True),
        ([(b"origin", b"http://localhost")], True),
        ([(b"origin", b"https://evil.example")], False),
    ],
)
async def test_origin_validation(project_id, token, headers, accepted, settings):
    settings.ALLOWED_HOSTS = ["localhost"]
    application = OriginValidatorAllowingNonBrowsers(websocket_application)
    communicator = WebsocketCommunicator(
        application, f"/ws/projects/{project_id}?token={token}", headers=headers
    )
    connected, _ = await communicator.connect()
    assert connected is accepted
    await communicator.disconnect()


async def test_second_connection_of_a_client_closes_with_4429(project_id, token):
    first = await connect(project_id, token)
    assert (await first.receive_json_from())["type"] == "snapshot"
    second = await connect(project_id, token)
    assert await second.receive_json_from() == {
        "type": "error",
        "code": "rate_limited",
        "detail": "too many connections to this project from this client",
    }
    assert (await second.receive_output())["code"] == 4429
    await first.disconnect()
    third = await connect(project_id, token)  # the slot is free again
    assert (await third.receive_json_from())["type"] == "snapshot"
    await third.disconnect()


async def test_connection_limit_is_configurable(project_id, token, settings):
    settings.WS_CONNECTIONS_PER_PROJECT = 2
    first, second = await connect(project_id, token), await connect(project_id, token)
    assert (await first.receive_json_from())["type"] == "snapshot"
    assert (await second.receive_json_from())["type"] == "snapshot"
    await first.disconnect()
    await second.disconnect()


async def test_message_flood_closes_with_4429(project_id, token, monkeypatch):
    monkeypatch.setattr(limits, "MESSAGES", 3)
    communicator = await connect(project_id, token)
    await communicator.receive_json_from()
    for _ in range(4):
        await communicator.send_json_to({"type": "subscribe_speaking", "enabled": True})
    assert (await communicator.receive_json_from())["code"] == "rate_limited"
    assert (await communicator.receive_output())["code"] == 4429


async def test_stale_slots_expire(project_id, token):
    redis = streams.get_async_client()
    token_row = await database_sync_to_async(resolve_token)(token)
    key = f"dh:ws:conn:{project_id}:token:{token_row.pk}"
    await redis.zadd(key, {"crashed-worker": 1.0})  # heartbeat in 1970
    communicator = await connect(project_id, token)
    assert (await communicator.receive_json_from())["type"] == "snapshot"
    await communicator.disconnect()
    await redis.delete(key)
    await redis.aclose()


def test_client_id_prefers_token_then_session_then_user():
    class Row:
        pk = 7

    class Session:
        session_key = "abc"

    assert limits.client_id({"api_token": Row(), "session": Session()}) == "token:7"
    assert limits.client_id({"session": Session(), "user": Row()}) == "session:abc"
    assert limits.client_id({"user": Row()}) == "user:7"


def test_message_rate_window_slides(monkeypatch):
    clock = iter([0.0, 0.1, 0.2, 11.0])
    monkeypatch.setattr(limits.time, "monotonic", lambda: next(clock))
    rate = limits.MessageRate(limit=2, window_s=10)
    assert [rate.allow(), rate.allow(), rate.allow(), rate.allow()] == [True, True, False, True]
