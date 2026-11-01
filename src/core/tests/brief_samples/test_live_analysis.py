# SPDX-License-Identifier: AGPL-3.0-or-later
"""Manual job: the analysis phase of a brief sample on a real provider, with a budget cap.

Never runs in CI by default (`.github/workflows/live-agents.yml` runs it on demand):

    DH_LIVE_AGENTS=1 ANTHROPIC_API_KEY=... uv run pytest -s \\
        src/core/tests/brief_samples/test_live_analysis.py

Variables: `DH_LIVE_PROVIDER` (default `anthropic`), `DH_LIVE_MODEL` (default
`claude-sonnet-5-5`, used for every chat profile), `DH_LIVE_BRIEF` (a file stem of
`briefs/`, default `gymbook`), `DH_LIVE_BUDGET_EUR` (default 1.00). Before every LLM call
the project's spend is compared with the cap and the turn stops when it is reached.
Questions are answered with their default assumptions; the job stops at the
`approve_requirements` gate, checks the artifacts' structure and prints tokens and cost.
"""

import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from django.db.models import Sum

from dexterhouse.apps.agents.models import AgentTurn
from dexterhouse.apps.agents.services import turns as turns_module
from dexterhouse.apps.gateway.models import LLMCall, ModelProfile
from dexterhouse.apps.gateway.providers import ProviderError
from dexterhouse.apps.projects.models import Project
from tests.brief_samples import structure
from tests.workflows.conftest import drain, open_gate

pytestmark = [
    pytest.mark.skipif(not os.environ.get("DH_LIVE_AGENTS"), reason="DH_LIVE_AGENTS not set"),
    pytest.mark.django_db(transaction=True),
]
CREDENTIALS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openai-compatible": "OPENAI_COMPATIBLE_BASE_URL",
    "ollama": "",
    "anthropic-cli": "",
    "fake": "",  # checks the harness itself with the demo responder (model `fake-model`)
}


def spent(project: Project) -> Decimal:
    return LLMCall.objects.filter(project=project).aggregate(c=Sum("cost"))["c"] or Decimal(0)


@pytest.fixture
def live_runtime(builtin_runtime, organization, monkeypatch):
    provider = os.environ.get("DH_LIVE_PROVIDER", "anthropic")
    credential = CREDENTIALS.get(provider)
    if credential is None:
        pytest.skip(f"unknown provider {provider}")
    if credential and not os.environ.get(credential):
        pytest.skip(f"{credential} not set")
    model = os.environ.get("DH_LIVE_MODEL", "claude-sonnet-5-5")
    ModelProfile.objects.filter(organization=organization, project=None).exclude(
        profile="embed"
    ).update(provider=provider, model=model)
    cap = Decimal(os.environ.get("DH_LIVE_BUDGET_EUR", "1.00"))
    generate = turns_module.generate

    def capped(**kwargs):
        project = Project.objects.get(pk=kwargs["ctx"].project_id)
        if spent(project) >= cap:
            raise ProviderError(f"live budget cap of {cap} EUR reached", code="configuration")
        return generate(**kwargs)

    monkeypatch.setattr(turns_module, "generate", capped)
    return provider, model, cap


def test_analysis_on_a_real_provider(client, live_runtime, capsys):
    provider, model, cap = live_runtime
    stem = os.environ.get("DH_LIVE_BRIEF", "gymbook")
    sample = yaml.safe_load((Path(__file__).parent / "briefs" / f"{stem}.yaml").read_text())
    body = {"name": sample["name"], "brief": sample["brief"], "budget": str(cap)}
    body["execution_mode"] = "supervised"
    response = client.post("/api/v1/projects", body, format="json")
    project = Project.objects.get(pk=response.json()["id"])
    assert client.post(f"/api/v1/projects/{project.id}/start").status_code == 200

    gate = None
    for _ in range(3):
        drain(project)
        gate = open_gate(project)
        if gate is None or gate.type != "question":
            break
        answers = [
            {"question_id": q["id"], "answer": q["default_assumption"]}
            for q in gate.payload["questions"]
        ]
        client.post(f"/api/v1/gates/{gate.id}/decide", {"answers": answers}, format="json")

    lines = [f"\nLive analysis: {sample['name']} on {provider}/{model}, cap {cap} EUR"]
    for turn in AgentTurn.objects.filter(project=project).order_by("created_at"):
        lines.append(
            f"- turn {turn.purpose}: {turn.status}, {turn.input_tokens} in / "
            f"{turn.output_tokens} out / {turn.cached_tokens} cached, {turn.cost} EUR, "
            f"{turn.tool_calls_count} tool calls {turn.error_code or ''}"
        )
    lines.append(f"Total: {spent(project)} EUR")
    with capsys.disabled():
        sys.stdout.write("\n".join(lines) + "\n")

    assert spent(project) <= cap * Decimal("1.5"), "one call may overshoot, not more"
    assert gate is not None, "the analysis did not reach a gate"
    assert gate.gate_id == "approve_requirements", gate.gate_id
    structure.assert_artifacts_are_well_formed(project)
    structure.assert_analysis(project)
