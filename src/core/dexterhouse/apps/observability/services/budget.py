# SPDX-License-Identifier: AGPL-3.0-or-later
"""Project and organization budgets (F-012, flows F7 in ux_2d_flows.md).

- `check_before_call` runs before every provider call (`gateway.services.complete`): an
  exhausted project or organization budget refuses the call with `BudgetExceededError` and
  puts the project in `waiting(budget)`. The agent turn stays resumable: no work is lost.
- `record_spend` runs after every priced call: it recomputes `Project.spent` and
  `Organization.spent_month` from `LLMCall` and emits `budget.warning` (80 %) and, at 100 %,
  calls `on_budget_exhausted` (pause + escalation gate + `budget.exceeded`).
- Raising the budget (`on_project_budget_changed`, `on_org_budget_changed`) closes the budget
  gate with `decision: retry` and resumes the project.
"""

import uuid
from decimal import Decimal
from typing import Any

import structlog
from django.db import transaction

from dexterhouse.apps.accounts.models import Organization
from dexterhouse.apps.gateway.providers.base import ProviderError
from dexterhouse.apps.observability.services import costs
from dexterhouse.apps.projects.models import Project, ProjectStatus, WaitingReason
from dexterhouse.apps.projects.services.actors import SYSTEM, emit, user_actor
from dexterhouse.apps.projects.services.transitions import transition

logger = structlog.get_logger(__name__)

WARNING_PCT = 80
BUDGET_GATE_ID = "budget"
BUDGET_REASON = "budget"
ACTIVE = (ProjectStatus.RUNNING, ProjectStatus.WAITING, ProjectStatus.PAUSED)


class BudgetExceededError(ProviderError):
    """The project's or organization's budget is exhausted: no provider call is made.

    Not retryable by the gateway; the agents runtime keeps the turn resumable and the
    workflow engine re-queues the step without consuming an attempt.
    """

    def __init__(self, scope: str, spent: Decimal, budget: Decimal) -> None:
        super().__init__(
            f"{scope} budget exhausted: {spent} of {budget} EUR", code="budget", retryable=False
        )
        self.scope = scope
        self.spent = spent
        self.budget = budget


def _exhausted(spent: Decimal, budget: Decimal | None) -> bool:
    return budget is not None and Decimal(spent) >= Decimal(budget)


def _crossed(old: Decimal, new: Decimal, limit: Decimal) -> bool:
    return Decimal(old) < limit <= Decimal(new)


# Before a call ---------------------------------------------------------------------------


def check_before_call(organization_id: uuid.UUID, project_id: uuid.UUID) -> None:
    """Refuse the call when a budget is exhausted (the single pre-call hook of the gateway).

    Raises:
        BudgetExceededError: project `spent >= budget` or organization month spend at or over
            `budget_monthly`; the project is moved to `waiting(budget)` first.
    """
    project = Project.objects.only("id", "spent", "budget").get(pk=project_id)
    if _exhausted(project.spent, project.budget):
        _refuse(project_id, "project")
        raise BudgetExceededError("project", project.spent, project.budget)
    org = Organization.objects.only("id", "spent_month", "budget_monthly").get(pk=organization_id)
    if _exhausted(org.spent_month, org.budget_monthly):
        _refuse(project_id, "organization")
        raise BudgetExceededError("organization", org.spent_month, org.budget_monthly)


def _refuse(project_id: uuid.UUID, scope: str) -> None:
    with transaction.atomic():
        project = Project.objects.select_for_update().get(pk=project_id)
        if scope == "project":
            on_budget_exhausted(project)
        else:
            _wait_for_budget(project, gate_id=None)
    logger.warning("budget.call_refused", project_id=str(project_id), scope=scope)


# After a call ----------------------------------------------------------------------------


def record_spend(organization_id: uuid.UUID, project_id: uuid.UUID) -> None:
    """Recompute project and organization spend from `LLMCall`; emit threshold events.

    Idempotent (sums, not increments): safe to call again after a retry or a resumed turn.
    """
    with transaction.atomic():
        project = Project.objects.select_for_update().get(pk=project_id)
        old = project.spent
        project.spent, project.spent_unpriced_tokens = costs.project_totals(project_id)
        project.save(update_fields=["spent", "spent_unpriced_tokens", "updated_at"])
        budget = Decimal(project.budget)
        warn_at = budget * WARNING_PCT / 100
        if _crossed(old, project.spent, warn_at) and project.spent < budget:
            emit(
                project,
                "budget.warning",
                {"spent": project.spent, "budget": budget, "pct": WARNING_PCT},
            )
        if _crossed(old, project.spent, budget):
            on_budget_exhausted(project)
        _record_org_spend(organization_id, project)


def _record_org_spend(organization_id: uuid.UUID, project: Project) -> None:
    org = Organization.objects.select_for_update().get(pk=organization_id)
    old = org.spent_month
    org.spent_month = costs.organization_month_spend(organization_id)
    org.save(update_fields=["spent_month", "updated_at"])
    if org.budget_monthly is None:
        return
    limit = Decimal(org.budget_monthly)
    payload = {"spent_month": org.spent_month, "budget_monthly": limit}
    if _crossed(old, org.spent_month, limit * WARNING_PCT / 100) and org.spent_month < limit:
        emit(project, "budget.org_warning", payload)
    if _crossed(old, org.spent_month, limit):
        emit(project, "budget.org_exceeded", payload)


# 100 % -------------------------------------------------------------------------------------


def on_budget_exhausted(project: Project) -> Any:
    """Hook point for the escalation service of E-06 (human in the loop).

    Today: open (once) an `escalation` gate with `reason: budget` on the active phase, move
    the project to `waiting(budget)` and emit `budget.exceeded`. When E-06 lands
    `workflows.services.escalate(project, reason, payload)`, replace the gate creation below
    with that call. The caller holds the project row lock. Returns the gate (or None when
    the project has no process run yet).
    """
    from dexterhouse.apps.workflows.engine import common
    from dexterhouse.apps.workflows.models import GateType

    gate = open_budget_gate(project)
    if gate is None:
        phase_run = _active_phase_run(project)
        if phase_run is None:
            _wait_for_budget(project, gate_id=None)
            return None
        payload = common.GatePayload(
            title="Budget exhausted",
            summary=(
                f"The project spent {project.spent} EUR of its {project.budget} EUR budget. "
                "Raise the budget to continue, or drop the project."
            ),
            reason=BUDGET_REASON,
        )
        gate = common.open_gate(
            phase_run,
            gate_id=BUDGET_GATE_ID,
            type=GateType.ESCALATION,
            payload=payload,
            block=False,
        )
        emit(
            project,
            "budget.exceeded",
            {"spent": project.spent, "budget": project.budget, "gate_id": gate.id},
            correlation_id=gate.id,
        )
    _wait_for_budget(project, gate_id=gate.id)
    return gate


def open_budget_gate(project: Project) -> Any:
    from dexterhouse.apps.workflows.models import Gate, GateStatus

    return Gate.objects.filter(
        project=project, gate_id=BUDGET_GATE_ID, status=GateStatus.OPEN
    ).first()


def is_budget_gate(gate: Any) -> bool:
    return gate.gate_id == BUDGET_GATE_ID and (gate.payload or {}).get("reason") == BUDGET_REASON


def _active_phase_run(project: Project) -> Any:
    from dexterhouse.apps.workflows.models import PhaseRun, PhaseStatus

    rows = PhaseRun.objects.filter(process_run__project=project).select_related("process_run")
    active = rows.filter(
        status__in=(PhaseStatus.RUNNING, PhaseStatus.WAITING_GATE, PhaseStatus.REOPENED)
    )
    row = active.order_by("position").first() or rows.order_by("-position").first()
    if row is not None:
        row.process_run.project = project
    return row


def _wait_for_budget(project: Project, *, gate_id: Any) -> None:
    """running/waiting(gate) -> waiting(budget); a paused project stays paused."""
    if project.status == ProjectStatus.RUNNING:
        transition(project, ProjectStatus.WAITING, waiting_reason=WaitingReason.BUDGET)
    elif project.status == ProjectStatus.WAITING and project.waiting_reason != "budget":
        project.waiting_reason = WaitingReason.BUDGET
        project.save(update_fields=["waiting_reason", "updated_at"])
    else:
        return
    emit(project, "project.waiting", {"reason": "budget", "gate_id": gate_id})


# Raising the budget ------------------------------------------------------------------------


def on_project_budget_changed(project: Project, user: Any) -> None:
    """After `PATCH /projects/{id}` with a new budget (caller holds the row lock)."""
    if not _exhausted(project.spent, project.budget):
        _close_budget_gate(project, user, decision="retry")
        _maybe_resume(project)


def on_org_budget_changed(organization: Organization) -> list[uuid.UUID]:
    """After `PUT /organization/budget`: resume projects that waited only for the org."""
    resumed = []
    if _exhausted(organization.spent_month, organization.budget_monthly):
        return resumed
    waiting = Project.objects.filter(
        organization=organization, status=ProjectStatus.WAITING, waiting_reason="budget"
    ).values_list("id", flat=True)
    for project_id in list(waiting):
        with transaction.atomic():
            project = Project.objects.select_for_update().get(pk=project_id)
            if _exhausted(project.spent, project.budget) or open_budget_gate(project):
                continue
            if _maybe_resume(project):
                resumed.append(project.id)
    return resumed


def ensure_can_resume(project: Project) -> None:
    """`POST /projects/{id}/resume` while a budget is still at 100 % → 402."""
    from dexterhouse.common.errors import BudgetExhaustedError

    if _exhausted(project.spent, project.budget):
        raise BudgetExhaustedError(
            f"the project spent {project.spent} of {project.budget} EUR: raise the budget first"
        )
    org = project.organization
    if _exhausted(org.spent_month, org.budget_monthly):
        raise BudgetExhaustedError("the organization's monthly budget is exhausted")


def ensure_org_can_start(organization: Organization) -> None:
    """`POST /projects/{id}/start` with the organization budget exhausted → 402 (flow F1)."""
    from dexterhouse.common.errors import BudgetExhaustedError

    org = Organization.objects.only("spent_month", "budget_monthly").get(pk=organization.pk)
    if _exhausted(org.spent_month, org.budget_monthly):
        raise BudgetExhaustedError("the organization's monthly budget is exhausted")


def decide_budget_gate(run: Any, gate: Any, user: Any, *, decision=None, comment=None, **_: Any):
    """`POST /gates/{id}/decide` on the budget gate: `retry` (budget raised) or `drop`."""
    from dexterhouse.apps.workflows.engine import common
    from dexterhouse.apps.workflows.models import GateStatus, PhaseRun
    from dexterhouse.common.errors import (
        BudgetExhaustedError,
        InvalidTransitionError,
        ValidationFailedError,
    )

    project = run.project
    if gate.status != GateStatus.OPEN:
        raise InvalidTransitionError(f"Gate already decided at {gate.decided_at}")
    if decision not in ("retry", "drop"):
        raise ValidationFailedError(
            "invalid decision for a budget gate",
            [{"field": "decision", "message": "one of drop, retry"}],
        )
    if decision == "retry":
        if _exhausted(project.spent, project.budget):
            raise BudgetExhaustedError("raise the budget before retrying")
        _close_budget_gate(project, user, decision="retry", comment=comment, gate=gate)
        _maybe_resume(project)
        return "project_resumed"
    common.decide(gate, GateStatus.REJECTED, "drop", user=user, comment=comment)
    common.gate_decided_event(gate, "phase_failed", actor=user_actor(user))
    row = PhaseRun.objects.get(pk=gate.phase_run_id)
    row.process_run = run
    common.fail_phase(row, "budget_exhausted", comment or "")
    return "phase_failed"


def _close_budget_gate(project: Project, user: Any, *, decision: str, comment=None, gate=None):
    from dexterhouse.apps.workflows.engine import common
    from dexterhouse.apps.workflows.models import GateStatus

    gate = gate or open_budget_gate(project)
    if gate is None:
        return
    gate.project = project
    common.decide(gate, GateStatus.APPROVED, decision, user=user, comment=comment)
    common.gate_decided_event(
        gate, "project_resumed", actor=user_actor(user) if user is not None else SYSTEM
    )


def _maybe_resume(project: Project) -> bool:
    """waiting(budget) -> running (or waiting(gate)), re-dispatching the queued steps."""
    from dexterhouse.apps.workflows.engine import start
    from dexterhouse.apps.workflows.models import Gate, GateStatus, ProcessRun

    if project.status != ProjectStatus.WAITING or project.waiting_reason != "budget":
        return False
    org = Organization.objects.get(pk=project.organization_id)
    if _exhausted(org.spent_month, org.budget_monthly):
        return False
    if Gate.objects.filter(project=project, status=GateStatus.OPEN).exists():
        project.waiting_reason = WaitingReason.GATE
        project.save(update_fields=["waiting_reason", "updated_at"])
    else:
        transition(project, ProjectStatus.RUNNING)
    emit(project, "project.resumed", {"reason": "budget"})
    run = ProcessRun.objects.select_for_update().filter(project=project).first()
    if run is not None:
        run.project = project
        start.resume_run(run)
    return True
