# SPDX-License-Identifier: AGPL-3.0-or-later
"""package.*, budget.*, provider.*, security.* payloads.

See contracts/events/packages_budget_security.md.
"""

import uuid
from decimal import Decimal
from typing import Literal

from pydantic import Field

from dexterhouse.apps.events.schemas.base import EventPayload
from dexterhouse.apps.events.schemas.common import _Strict

PackageKind = Literal["agent", "tool", "process"]

# package.*


class PackageInstalling(EventPayload):
    event_type = "package.installing"
    actors = ("user", "system")

    install_id: uuid.UUID
    name: str
    version: str
    kind: PackageKind
    source: Literal["builtin", "marketplace", "local"]


class Permission(_Strict):
    id: str
    risk: Literal["low", "medium", "high"]
    description: str


class PackageConsentRequested(EventPayload):
    event_type = "package.consent_requested"

    install_id: uuid.UUID
    name: str
    permissions: list[Permission]


class PackageInstalled(EventPayload):
    event_type = "package.installed"

    package_id: uuid.UUID
    version_id: uuid.UUID
    name: str
    version: str
    kind: PackageKind
    roles: list[str] = Field(default_factory=list)  # agent packages only


class PackageRejected(EventPayload):
    event_type = "package.rejected"

    install_id: uuid.UUID
    name: str
    reason: Literal["hash", "schema", "compat", "scan", "declined"]
    errors: list[str]


class _PackageToggled(EventPayload):
    actors = ("user", "system")

    package_id: uuid.UUID
    name: str
    reason: str | None = None


class PackageDisabled(_PackageToggled):
    event_type = "package.disabled"


class PackageEnabled(_PackageToggled):
    event_type = "package.enabled"


class PackageRemoved(_PackageToggled):
    event_type = "package.removed"


class PackageUpdateAvailable(EventPayload):
    """Emitted by the periodic registry check (Celery beat)."""

    event_type = "package.update_available"

    package_id: uuid.UUID
    name: str
    current: str
    latest: str
    compat_ok: bool


# budget.*


class BudgetEstimated(EventPayload):
    event_type = "budget.estimated"

    low: Decimal
    high: Decimal
    basis: Literal["static", "history"]


class BudgetWarning(EventPayload):
    event_type = "budget.warning"

    spent: Decimal
    budget: Decimal
    pct: int


class BudgetExceeded(EventPayload):
    event_type = "budget.exceeded"

    spent: Decimal
    budget: Decimal
    gate_id: uuid.UUID


class _OrgBudget(EventPayload):
    spent_month: Decimal
    budget_monthly: Decimal


class BudgetOrgWarning(_OrgBudget):
    event_type = "budget.org_warning"


class BudgetOrgExceeded(_OrgBudget):
    event_type = "budget.org_exceeded"


# provider.*


class ProviderDegraded(EventPayload):
    event_type = "provider.degraded"

    provider: str
    reason: Literal["rate_limit", "error", "timeout"]
    action: Literal["retry", "downgrade", "wait"]
    profile: Literal["strong", "balanced", "fast", "embed"]


class ProviderRecovered(EventPayload):
    event_type = "provider.recovered"

    provider: str


# security.*


class SecurityViolation(EventPayload):
    event_type = "security.violation"

    agent_id: uuid.UUID
    turn_id: uuid.UUID
    tool: str
    kind: Literal["tool_not_allowed", "args_policy", "workspace_escape", "network_blocked"]
    count_in_turn: int


class SecurityTurnBlocked(EventPayload):
    event_type = "security.turn_blocked"

    agent_id: uuid.UUID
    turn_id: uuid.UUID
    violations: int  # count in the turn
