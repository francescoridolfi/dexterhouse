# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST v1 (read side): the team of a project, agent turns and tool calls (agents_packages.md).

Hiring, releasing and editing agents (flow F9) are not exposed yet.
"""

import uuid
from typing import Any

from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404
from rest_framework.request import Request
from rest_framework.response import Response

from dexterhouse.apps.agents.models import AgentInstance, AgentTurn, ToolCall
from dexterhouse.apps.projects.api.views import READ, get_project
from dexterhouse.common.api import ApiView, OrgContext

RESULT_EXCERPT = 2_000


def _ts(value: Any) -> str | None:
    return value.isoformat() if value else None


def agent_json(agent: AgentInstance, stats: dict[str, Any] | None = None) -> dict[str, Any]:
    stats = stats or {}
    return {
        "id": str(agent.id),
        "project": str(agent.project_id),
        "role": agent.role,
        "display_name": agent.display_name,
        "package": {"name": agent.package_name, "version": agent.package_version},
        "placeholder": not agent.package_path,
        "source": agent.source,
        "model_profile": agent.model_profile,
        "allowed_tools": agent.allowed_tools,
        "room": agent.room,
        "avatar": agent.avatar,
        "status": agent.status,
        "turns_count": stats.get("turns", 0),
        "spent": str(stats.get("cost") or 0),
        "hired_at": _ts(agent.hired_at),
        "released_at": _ts(agent.released_at),
    }


def turn_json(turn: AgentTurn, *, detail: bool = False) -> dict[str, Any]:
    data = {
        "id": str(turn.id),
        "agent": str(turn.agent_instance_id),
        "phase_run": str(turn.phase_run_id) if turn.phase_run_id else None,
        "task": str(turn.task_id) if turn.task_id else None,
        "step": turn.step,
        "status": turn.status,
        "purpose": turn.purpose,
        "tool_calls_count": turn.tool_calls_count,
        "input_tokens": turn.input_tokens,
        "output_tokens": turn.output_tokens,
        "cached_tokens": turn.cached_tokens,
        "cost": str(turn.cost),
        "profile_used": turn.profile_used,
        "attempt": turn.attempt,
        "error_code": turn.error_code or None,
        "started_at": _ts(turn.started_at),
        "finished_at": _ts(turn.finished_at),
        "created_at": _ts(turn.created_at),
    }
    if detail:
        data |= {
            "context_manifest": turn.context_manifest,
            "messages": turn.messages,
            "output": turn.output,
            "error_detail": turn.error_detail or None,
            "tool_calls": [tool_call_json(c) for c in turn.tool_calls.order_by("seq")],
        }
    return data


def tool_call_json(call: ToolCall) -> dict[str, Any]:
    result = call.result
    text = str(result) if result is not None else None
    return {
        "seq": call.seq,
        "tool": call.tool,
        "arguments": call.arguments,
        "allowed": call.allowed,
        "status": call.status,
        "denied_reason": call.denied_reason or None,
        "duration_ms": call.duration_ms,
        "result_excerpt": text[:RESULT_EXCERPT] if text else None,
        "truncated": bool(text and len(text) > RESULT_EXCERPT),
    }


def _stats(project_id: uuid.UUID) -> dict[uuid.UUID, dict[str, Any]]:
    rows = (
        AgentTurn.objects.filter(project_id=project_id)
        .values("agent_instance_id")
        .annotate(turns=Count("id"), cost=Sum("cost"))
    )
    return {r["agent_instance_id"]: r for r in rows}


def _agent(ctx: OrgContext, agent_id: uuid.UUID) -> AgentInstance:
    return get_object_or_404(AgentInstance, pk=agent_id, organization=ctx.organization)


class ProjectAgentsView(ApiView):
    def get(self, request: Request, project_id: uuid.UUID) -> Response:
        project = get_project(self.require(*READ), project_id)
        stats = _stats(project.id)
        rows = AgentInstance.objects.filter(project=project).order_by("role", "hired_at")
        return Response({"results": [agent_json(a, stats.get(a.id)) for a in rows]})


class AgentDetailView(ApiView):
    def get(self, request: Request, agent_id: uuid.UUID) -> Response:
        agent = _agent(self.require(*READ), agent_id)
        data = agent_json(agent, _stats(agent.project_id).get(agent.id))
        data["turns"] = [turn_json(t) for t in agent.turns.order_by("-created_at")[:20]]
        return Response(data)


class AgentTurnsView(ApiView):
    def get(self, request: Request, agent_id: uuid.UUID) -> Response:
        agent = _agent(self.require(*READ), agent_id)
        return self.paginate(AgentTurn.objects.filter(agent_instance=agent), turn_json)


class ProjectTurnsView(ApiView):
    def get(self, request: Request, project_id: uuid.UUID) -> Response:
        project = get_project(self.require(*READ), project_id)
        rows = AgentTurn.objects.filter(project=project)
        for name in ("status", "phase_run", "task"):
            if value := request.query_params.get(name):
                rows = rows.filter(**{name: value})
        return self.paginate(rows, turn_json)


class TurnDetailView(ApiView):
    def get(self, request: Request, turn_id: uuid.UUID) -> Response:
        ctx = self.require(*READ)
        turn = get_object_or_404(AgentTurn, pk=turn_id, organization=ctx.organization)
        return Response(turn_json(turn, detail=True))
