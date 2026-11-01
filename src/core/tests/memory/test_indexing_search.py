# SPDX-License-Identifier: AGPL-3.0-or-later
import uuid

import pytest
from django.db import connections
from mcp import Client

from dexterhouse.apps.gateway.embeddings import FakeEmbedder
from dexterhouse.apps.memory.mcp_server import build_server, main, wrap_untrusted
from dexterhouse.apps.memory.models import MemoryChunk
from dexterhouse.apps.memory.services.indexing import index_artifact, index_comment
from dexterhouse.apps.memory.services.search import REINDEX_REQUIRED, recent, search
from dexterhouse.apps.memory.tasks import index_artifact_task, index_comment_task

from .conftest import ARCHITECTURE

pytestmark = pytest.mark.django_db


def index(organization, project_id, embedder, **kwargs):
    defaults = {
        "artifact_id": uuid.uuid4(),
        "version": 1,
        "kind": "architecture",
        "name": "architecture.md",
    }
    return index_artifact(
        organization_id=organization.id,
        project_id=project_id,
        embedder=embedder,
        **(defaults | kwargs),
    )


def test_index_is_incremental_by_version(organization, project_id, embedder):
    artifact = uuid.uuid4()
    first = index(organization, project_id, embedder, artifact_id=artifact, content=ARCHITECTURE)
    assert first.created == 3
    assert index(
        organization, project_id, embedder, artifact_id=artifact, content=ARCHITECTURE
    ).skipped
    second = index(
        organization,
        project_id,
        embedder,
        artifact_id=artifact,
        version=2,
        content="## Only\n\nnew",
    )
    assert (second.created, second.replaced) == (1, 3)
    assert set(MemoryChunk.objects.values_list("artifact_version", flat=True)) == {2}
    stale = index(
        organization, project_id, embedder, artifact_id=artifact, version=1, content=ARCHITECTURE
    )
    assert stale.skipped


def test_search_ranks_relevant_chunks_and_filters(organization, project_id, embedder, user):
    from dexterhouse.apps.projects.services.projects import create_project

    other = create_project(organization, user, {"name": "Other", "brief": "b", "budget": "1"})
    arch = uuid.uuid4()
    index(organization, project_id, embedder, artifact_id=arch, content=ARCHITECTURE)
    index(
        organization,
        project_id,
        embedder,
        kind="stack",
        name="stack.yaml",
        data={"language": "python", "framework": "django"},
    )
    index(organization, other.id, embedder, content="waitlist FIFO email other project")

    result = search(
        project_id=project_id, query="waitlist FIFO email", embedder=embedder, k=3, min_score=0.1
    )
    assert result.hits[0].heading == "Data model"
    assert result.hits[0].as_dict()["artifact"]["name"] == "architecture.md"
    assert all(h.artifact_id != "other" for h in result.hits)
    only_stack = search(
        project_id=project_id,
        query="python django",
        embedder=embedder,
        kinds=["stack"],
        min_score=0.1,
    )
    assert {h.kind for h in only_stack.hits} == {"stack"}
    excluded = search(
        project_id=project_id,
        query="waitlist",
        embedder=embedder,
        exclude_artifacts=[arch],
        min_score=0,
    )
    assert all(h.artifact_id != str(arch) for h in excluded.hits)
    assert (
        search(project_id=project_id, query="zebra quantum", embedder=embedder, min_score=0.9).hits
        == []
    )


def test_gate_comments_and_lessons_weigh_more(organization, project_id, embedder):
    index(
        organization,
        project_id,
        embedder,
        content="## Waitlist\n\nThe waitlist sends email in FIFO order.",
    )
    comment = index_comment(
        organization_id=organization.id,
        project_id=project_id,
        source_id=uuid.uuid4(),
        text="Waitlist must be FIFO with email notification.",
        embedder=embedder,
    )
    assert comment.created == 1
    retro = "## What went well\n\nCI.\n\n## Lessons learned\n\nWrite the waitlist tests first."
    index(
        organization,
        project_id,
        embedder,
        kind="retrospective",
        name="retrospective.md",
        content=retro,
    )
    weights = dict(MemoryChunk.objects.values_list("kind", "weight").distinct())
    assert weights["gate_comment"] == 1.5
    assert weights["retro_lesson"] == 1.5
    assert weights["retrospective"] == 1.0
    hits = search(
        project_id=project_id, query="waitlist FIFO email", embedder=embedder, min_score=0.1
    ).hits
    assert hits[0].kind == "gate_comment"
    with pytest.raises(ValueError, match="unsupported"):
        index_comment(
            organization_id=organization.id,
            project_id=project_id,
            source_id=uuid.uuid4(),
            text="x",
            kind="brief",
        )


def test_other_embedder_requires_reindex(organization, project_id, embedder):
    index(organization, project_id, embedder, content=ARCHITECTURE)

    class Other(FakeEmbedder):
        name = "ollama/mxbai-embed-large"

    result = search(project_id=project_id, query="waitlist", embedder=Other())
    assert result.hits == []
    assert result.warnings == [REINDEX_REQUIRED]
    assert search(project_id=uuid.uuid4(), query="x", embedder=embedder).warnings == []


def test_recent_and_tasks(organization, project_id, fake_embed_profile):
    created = index_artifact_task(
        str(organization.id),
        str(project_id),
        str(uuid.uuid4()),
        1,
        "brief",
        "brief.md",
        content="A gym booking app.",
    )
    assert created == 1
    assert (
        index_comment_task(
            str(organization.id), str(project_id), str(uuid.uuid4()), "Use Tailwind", "note"
        )
        == 1
    )
    items = recent(project_id=project_id)
    assert [i["artifact"]["kind"] for i in items] == ["note", "brief"]
    assert (
        recent(project_id=project_id, kinds=["brief"], limit=1)[0]["excerpt"]
        == "A gym booking app."
    )


def test_untrusted_wrapping():
    assert wrap_untrusted("x", "web") == "<<untrusted source=web>>\nx\n<</untrusted>>"


@pytest.mark.django_db(transaction=True)
async def test_mcp_server_search(organization, project_id, fake_embed_profile):
    from asgiref.sync import sync_to_async

    await sync_to_async(index_artifact)(
        organization_id=organization.id,
        project_id=project_id,
        artifact_id=uuid.uuid4(),
        version=1,
        kind="requirements",
        name="requirements.md",
        content="## F-07 Waitlist\n\nFIFO waitlist with email.",
        untrusted=True,
    )
    async with Client(build_server(project_id, organization.id)) as client:
        names = {t.name for t in (await client.list_tools()).tools}
        assert names == {"memory_search", "memory_recent"}
        result = await client.call_tool("memory_search", {"query": "waitlist email", "k": 2})
        hits = result.structured_content["hits"]
        assert hits[0]["artifact"]["name"] == "requirements.md"
        assert hits[0]["content"].startswith("<<untrusted source=requirements.md>>")
        listed = await client.call_tool("memory_recent", {})
        assert listed.structured_content["items"][0]["artifact"]["kind"] == "requirements"
    await sync_to_async(connections.close_all)()  # the worker thread's connection


def test_main_requires_project(monkeypatch, capsys):
    monkeypatch.delenv("DH_PROJECT_ID", raising=False)
    assert main() == 1
    assert "DH_PROJECT_ID" in capsys.readouterr().err


def test_index_task_skips_without_embedder_and_retries_transient_errors(
    organization, project_id, monkeypatch
):
    from dexterhouse.apps.gateway.providers import ProviderError
    from dexterhouse.apps.memory import tasks

    args = (str(organization.id), str(project_id), str(uuid.uuid4()), 1, "brief")

    def unavailable(*a, **k):
        raise ProviderError("no embedder", code="configuration")

    monkeypatch.setattr(tasks, "resolve_embedder", unavailable)
    assert tasks.index_artifact_task(*args, content="x") == 0

    def down(*a, **k):
        raise ProviderError("down", code="provider", retryable=True)

    monkeypatch.setattr(tasks, "resolve_embedder", down)
    with pytest.raises(ProviderError):
        tasks.index_artifact_task(*args, content="x")
