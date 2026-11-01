# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST v1: phases, tasks, gates (contracts/api/workflow.md)."""

import uuid

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

from dexterhouse.apps.accounts.models import Role, Scope
from dexterhouse.apps.projects.api.serializers import artifact_json
from dexterhouse.apps.projects.api.views import ADMIN, READ, WRITE, get_project
from dexterhouse.apps.workflows import services
from dexterhouse.apps.workflows.api.serializers import (
    DecideInput,
    TaskInput,
    gate_json,
    phase_json,
    step_json,
    task_json,
)
from dexterhouse.apps.workflows.models import Gate, GateStatus, GateType, PhaseRun, Task
from dexterhouse.common.api import ApiView, OrgContext
from dexterhouse.common.api.pagination import AscendingCursorPage

DECIDE = (Role.ADMIN, Scope.GATES_DECIDE)
ANSWER = (Role.MEMBER, Scope.GATES_DECIDE)  # question gates: member+ (ux_2d_flows.md F3)
GATE_RELATED = ("decided_by", "project", "phase_run")


def _phase(ctx: OrgContext, phase_id: uuid.UUID) -> PhaseRun:
    rows = PhaseRun.objects.filter(process_run__project__organization=ctx.organization)
    return get_object_or_404(rows.select_related("process_run"), pk=phase_id)


def _task(ctx: OrgContext, task_id: uuid.UUID) -> Task:
    return get_object_or_404(
        Task.objects.filter(project__organization=ctx.organization), pk=task_id
    )


def _gate(ctx: OrgContext, gate_id: uuid.UUID) -> Gate:
    rows = Gate.objects.filter(project__organization=ctx.organization).select_related(*GATE_RELATED)
    return get_object_or_404(rows, pk=gate_id)


def _open_gate(phase: PhaseRun) -> Gate | None:
    return phase.gates.filter(status=GateStatus.OPEN).first()


class PhaseListView(ApiView):
    def get(self, request: Request, project_id: uuid.UUID) -> Response:
        project = get_project(self.require(*READ), project_id)
        rows = PhaseRun.objects.filter(process_run__project=project).select_related("process_run")
        return Response({"results": [phase_json(p, _open_gate(p)) for p in rows]})


class PhaseDetailView(ApiView):
    def get(self, request: Request, phase_id: uuid.UUID) -> Response:
        phase = _phase(self.require(*READ), phase_id)
        data = phase_json(phase, _open_gate(phase))
        data["turns"] = [step_json(s) for s in phase.step_runs.order_by("seq")]
        data["artifacts"] = [artifact_json(a) for a in phase.artifacts.order_by("created_at")]
        return Response(data)


class PhaseSkipView(ApiView):
    def post(self, request: Request, phase_id: uuid.UUID) -> Response:
        ctx = self.require(*ADMIN)
        phase = services.skip_phase(_phase(ctx, phase_id).id, ctx.user)
        return Response(phase_json(_phase(ctx, phase.id)))


class TaskListView(ApiView):
    def get(self, request: Request, project_id: uuid.UUID) -> Response:
        project = get_project(self.require(*READ), project_id)
        rows = Task.objects.filter(project=project)
        for name in ("status", "kind", "assigned_role"):
            if value := request.query_params.get(name):
                rows = rows.filter(**{name: value})
        return self.paginate(rows, task_json, page=AscendingCursorPage)

    def post(self, request: Request, project_id: uuid.UUID) -> Response:
        ctx = self.require(*WRITE)
        project = get_project(ctx, project_id)
        body = TaskInput(data=request.data)
        body.is_valid(raise_exception=True)
        task = services.add_task(project.id, ctx.user, body.validated_data)
        return Response(task_json(task), status=status.HTTP_201_CREATED)


class TaskDetailView(ApiView):
    def get(self, request: Request, task_id: uuid.UUID) -> Response:
        task = _task(self.require(*READ), task_id)
        data = task_json(task)
        data["children"] = [task_json(c) for c in task.children.order_by("iteration")]
        data["turns"] = [step_json(s) for s in task.step_runs.order_by("seq")]
        return Response(data)

    def patch(self, request: Request, task_id: uuid.UUID) -> Response:
        ctx = self.require(*WRITE)
        task = _task(ctx, task_id)
        body = TaskInput(data=request.data, partial=True)
        body.is_valid(raise_exception=True)
        fields = {k: v for k, v in body.validated_data.items() if k in request.data}
        return Response(task_json(services.update_task(task.id, ctx.user, fields)))


class TaskCancelView(ApiView):
    def post(self, request: Request, task_id: uuid.UUID) -> Response:
        ctx = self.require(*ADMIN)
        task = services.cancel_task(_task(ctx, task_id).id, ctx.user)
        return Response(task_json(task))


class GateInboxView(ApiView):
    def get(self, request: Request) -> Response:
        ctx = self.require(*READ)
        rows = Gate.objects.filter(project__organization=ctx.organization).select_related(
            *GATE_RELATED
        )
        for name in ("status", "type"):
            if value := request.query_params.get(name):
                rows = rows.filter(**{name: value})
        if value := request.query_params.get("project"):
            rows = rows.filter(project_id=value)
        return self.paginate(rows, gate_json)


class ProjectGatesView(ApiView):
    def get(self, request: Request, project_id: uuid.UUID) -> Response:
        project = get_project(self.require(*READ), project_id)
        rows = Gate.objects.filter(project=project).select_related(*GATE_RELATED)
        return self.paginate(rows, gate_json, page=AscendingCursorPage)


class GateDetailView(ApiView):
    def get(self, request: Request, gate_id: uuid.UUID) -> Response:
        gate = _gate(self.require(*READ), gate_id)
        data = gate_json(gate)
        ids = [a["id"] for a in gate.payload.get("artifacts", [])]
        data["artifacts"] = [
            artifact_json(a, content=True) for a in gate.project.artifacts.filter(pk__in=ids)
        ]
        return Response(data)


class GateDecideView(ApiView):
    def post(self, request: Request, gate_id: uuid.UUID) -> Response:
        gate = _gate(self.require(*ANSWER), gate_id)
        ctx = self.require(*(ANSWER if gate.type == GateType.QUESTION else DECIDE))
        body = DecideInput(data=request.data)
        body.is_valid(raise_exception=True)
        gate, next_ = services.decide(gate.id, ctx.user, **body.validated_data)
        data = {**gate_json(gate), "next": next_}
        if next_ == "tasks_created":
            data["tasks_created"] = [task_json(t) for t in services.created_by(gate)]
        return Response(data)
