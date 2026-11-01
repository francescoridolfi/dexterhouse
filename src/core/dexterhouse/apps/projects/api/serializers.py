# SPDX-License-Identifier: AGPL-3.0-or-later
"""Input validation and JSON views for projects, artifacts and notes."""

from typing import Any

from rest_framework import serializers

from dexterhouse.apps.projects.models import (
    Artifact,
    DataResidency,
    DeliveryMode,
    ExecutionMode,
    Note,
    Project,
)
from dexterhouse.apps.projects.services.artifacts import USER_KINDS
from dexterhouse.apps.workflows.models import Gate, GateStatus, PhaseRun, PhaseStatus

SECRET_SET = "***set***"  # noqa: S105  # nosec B105: placeholder shown instead of the token


def _ts(value: Any) -> str | None:
    return value.isoformat() if value else None


class ProjectInput(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    brief = serializers.CharField(max_length=20_000)
    process = serializers.RegexField(r"^[a-z0-9][a-z0-9-]{0,63}$", required=False)
    execution_mode = serializers.ChoiceField(choices=ExecutionMode.values, required=False)
    budget = serializers.DecimalField(max_digits=12, decimal_places=6, min_value=0)
    data_residency = serializers.ChoiceField(choices=DataResidency.values, required=False)
    remote_repo_url = serializers.URLField(
        max_length=500, required=False, allow_null=True, allow_blank=True
    )
    remote_token = serializers.CharField(
        max_length=500, required=False, allow_null=True, allow_blank=True, write_only=True
    )
    delivery_mode = serializers.ChoiceField(choices=DeliveryMode.values, required=False)
    gate_overrides = serializers.DictField(
        child=serializers.ChoiceField(choices=["always_required"]), required=False
    )
    model_profile_overrides = serializers.DictField(
        child=serializers.DictField(), required=False, allow_null=True
    )
    stack = serializers.DictField(required=False, allow_null=True)

    def validate_remote_repo_url(self, value: str | None) -> str | None:
        if value and not value.startswith("https://"):
            raise serializers.ValidationError("only https:// repositories are supported")
        return value or None


class ArtifactInput(serializers.Serializer):
    kind = serializers.ChoiceField(choices=sorted(USER_KINDS))
    name = serializers.CharField(max_length=200)
    content = serializers.CharField(
        required=False, allow_blank=True, default="", trim_whitespace=False
    )
    data = serializers.JSONField(required=False, allow_null=True, default=None)


class NoteInput(serializers.Serializer):
    content = serializers.CharField(max_length=10_000)
    phase_run = serializers.UUIDField(required=False, allow_null=True, default=None)


def project_json(project: Project, *, detail: bool = False) -> dict[str, Any]:
    run = getattr(project, "process_run", None) if project.status != "draft" else None
    phases = list(PhaseRun.objects.filter(process_run=run)) if run else []
    data = {
        "id": str(project.id),
        "organization": project.organization.slug,
        "name": project.name,
        "slug": project.slug,
        "status": project.status,
        "waiting_reason": project.waiting_reason,
        "execution_mode": project.execution_mode,
        "process": {"name": project.process_name, "version": project.process_version},
        "budget": str(project.budget),
        "spent": str(project.spent),
        "spent_unpriced_tokens": project.spent_unpriced_tokens,
        "data_residency": project.data_residency,
        "delivery_mode": project.delivery_mode,
        "remote_repo_url": project.remote_repo_url,
        "remote_token": SECRET_SET if project.remote_token else None,
        "gate_overrides": project.gate_overrides,
        "model_profile_overrides": project.model_profile_overrides,
        "open_gates_count": Gate.objects.filter(project=project, status=GateStatus.OPEN).count(),
        "current_phases": [
            p.phase_id
            for p in phases
            if p.status in (PhaseStatus.RUNNING, PhaseStatus.WAITING_GATE, PhaseStatus.REOPENED)
        ],
        "created_by": project.created_by.get_username(),
        "started_at": _ts(project.started_at),
        "completed_at": _ts(project.completed_at),
        "created_at": _ts(project.created_at),
        "updated_at": _ts(project.updated_at),
    }
    if detail:
        data |= {
            "brief": project.brief,
            "stack": project.stack,
            "workspace": None,  # runner workspaces arrive with E-05
            "team_summary": [],  # agent instances arrive with E-03
        }
    return data


def artifact_json(artifact: Artifact, *, content: bool = False) -> dict[str, Any]:
    data = {
        "id": str(artifact.id),
        "project": str(artifact.project_id),
        "kind": artifact.kind,
        "name": artifact.name,
        "version": artifact.version,
        "content_hash": artifact.content_hash,
        "phase_run": str(artifact.phase_run_id) if artifact.phase_run_id else None,
        "produced_by": {
            "role": artifact.produced_by_role or None,
            "turn_id": str(artifact.produced_by_turn_id) if artifact.produced_by_turn_id else None,
        },
        "created_at": _ts(artifact.created_at),
    }
    if content:
        data |= {"content": artifact.content, "data": artifact.data}
    return data


def note_json(note: Note) -> dict[str, Any]:
    return {
        "id": str(note.id),
        "project": str(note.project_id),
        "author": note.author.get_username(),
        "phase_run": str(note.phase_run_id) if note.phase_run_id else None,
        "content": note.content,
        "consumed": bool(note.consumed_by_turn_ids),
        "created_at": _ts(note.created_at),
    }
