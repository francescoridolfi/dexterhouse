# SPDX-License-Identifier: AGPL-3.0-or-later
"""Context documents in the turn inputs (docs/specs/context-documents.md, Agent inputs)."""

import pytest

from dexterhouse.apps.projects.services import context
from dexterhouse.apps.workflows.engine import steps
from dexterhouse.apps.workflows.models import StepRun
from dexterhouse.apps.workflows.runners.inputs import build_inputs, input_kinds

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def context_dir(settings, tmp_path):
    settings.CONTEXT_DIR = tmp_path / "context"


def _doc(project, user, name, text):
    doc = context.add_document(project, user, filename=name, content=text.encode())
    context.process_document(doc.id)  # the worker's part (on_commit does not run here)
    return doc


def _analyst(project):
    step = StepRun.objects.get(project=project, step="analyst")
    request = steps.claim(step.id)
    step.refresh_from_db()
    return request, step


def test_analyst_reads_processed_documents_whole_and_untrusted(started, user, settings):
    settings.WORKFLOWS_FAKE_RUNNER = {"ask_questions": False}
    project = started()
    _doc(project, user, "analysis.md", "# Analysis\n\nAnswer in 200 ms.")
    pending = context.add_document(project, user, filename="later.md", content=b"not yet")
    request, step = _analyst(project)
    assert "context" in input_kinds(request)
    docs = [a for a in build_inputs(request, step).artifacts if a.kind == "context"]
    assert [d.name for d in docs] == ["context/analysis.md"]
    assert docs[0].untrusted is True
    assert docs[0].data is None
    assert docs[0].content == "# Analysis\n\nAnswer in 200 ms."
    assert pending.name not in [d.name for d in docs]


def test_long_documents_enter_as_an_excerpt_with_the_memory_hint(started, user, settings):
    settings.WORKFLOWS_FAKE_RUNNER = {"ask_questions": False}
    project = started()
    _doc(project, user, "big.txt", "x" * 9000 + "LAST SENTENCE")
    request, step = _analyst(project)
    doc = next(a for a in build_inputs(request, step).artifacts if a.kind == "context")
    assert len(doc.content) < 2500
    assert doc.content.startswith("x" * 2000)
    assert "LAST SENTENCE" not in doc.content
    assert "memory.search" in doc.content


def test_deactivated_documents_and_other_roles(started, user, settings):
    settings.WORKFLOWS_FAKE_RUNNER = {"ask_questions": False}
    project = started()
    doc = _doc(project, user, "analysis.md", "text")
    context.deactivate_document(project, user, doc.name)
    request, step = _analyst(project)
    assert not [a for a in build_inputs(request, step).artifacts if a.kind == "context"]
    developer = request.model_copy(update={"role": "developer", "step": "developer"})
    assert "context" not in input_kinds(developer)
    architect = request.model_copy(update={"role": "architect", "step": "architect"})
    assert "context" in input_kinds(architect)
