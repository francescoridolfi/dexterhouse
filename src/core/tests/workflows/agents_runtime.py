# SPDX-License-Identifier: AGPL-3.0-or-later
"""The real agents runtime in workflow tests: `fake` gateway provider + test agent packages.

`respond` answers the `fake` provider (`settings.GATEWAY_FAKE_RESPONDER`): it finds the turn
from the request metadata, rebuilds the engine's `TurnRequest` from the step run and
replies with what `FakeTurnRunner` would produce. The first LLM call of a turn uses one of
the agent's tools when it has one (`project.ask` before asking, otherwise a read), so the
built-in MCP servers run for real; the second call returns the TurnOutput JSON.
"""

import json
import time
from typing import Any

from django.conf import settings

from dexterhouse.apps.agents.models import AgentTurn
from dexterhouse.apps.gateway.messages import CompletionRequest
from dexterhouse.apps.gateway.models import ModelProfile
from dexterhouse.apps.gateway.providers.fake import FakeResponse, FakeToolCall
from dexterhouse.apps.workflows.runner import TurnRequest
from dexterhouse.apps.workflows.runners.fake import FakeTurnRunner

AGENTS_RUNNER = "dexterhouse.apps.workflows.runners.agents.AgentsTurnRunner"
RESPONDER = "tests.workflows.agents_runtime.respond"
SKILLS = {"analyst": "brief-reading", "developer": "small-steps"}
READS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("project.artifacts", {}),
    ("project.tasks", {}),
    ("memory.search", {"query": "requirements", "k": 3}),
)


def use_fake_profiles(organization: Any) -> None:
    for profile, model in (
        ("strong", "fake-model"),
        ("balanced", "fake-model"),
        ("fast", "fake-model"),
        ("embed", "hash-1024"),
    ):
        ModelProfile.objects.get_or_create(
            organization=organization,
            profile=profile,
            project=None,
            defaults={"provider": "fake", "model": model},
        )


def respond(request: CompletionRequest) -> FakeResponse:
    turn = AgentTurn.objects.select_related("step_run", "agent_instance").get(
        pk=request.metadata["agent_turn_id"]
    )
    script = dict(settings.WORKFLOWS_FAKE_RUNNER)
    if delay := float(script.get("delay_s", 0)):
        time.sleep(delay)
    turn_request = TurnRequest.model_validate(turn.step_run.request)
    output = FakeTurnRunner(script)._output(turn_request)
    if not any(m.role == "assistant" for m in request.messages):
        call = _first_tool(output, turn.agent_instance.role, {t.name for t in request.tools})
        if call is not None:
            return FakeResponse(tool_calls=[call])
    return FakeResponse(text="Done.\n" + json.dumps(output))


def _first_tool(output: dict[str, Any], role: str, tools: set[str]) -> FakeToolCall | None:
    if output["status"] == "waiting_answers" and "project.ask" in tools:
        questions = next(a["data"]["questions"] for a in output["artifacts"])
        return FakeToolCall(id="ask", name="project.ask", args={"questions": questions})
    if role in SKILLS and "skills.read" in tools:
        return FakeToolCall(id="skill", name="skills.read", args={"name": SKILLS[role]})
    for name, args in READS:
        if name in tools:
            return FakeToolCall(id="read", name=name, args=args)
    if "project.artifact" in tools:
        return FakeToolCall(id="read", name="project.artifact", args={"kind": "brief"})
    return None
