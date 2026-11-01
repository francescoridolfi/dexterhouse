# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Recruiter's `team_proposal` as the planning gate and its actions see it.

The gate payload carries the proposals (`team`) so the 2D gate can show them as a table
next to the artifacts. After an approval decided by a person every proposal is installed
(the decision is the consent); after an automatic approval (autonomous mode) only the
proposals whose registry entry is `verified` with `risk: low` are, the others stay
proposals (F-008). The entry is read from the index, never from the proposal itself.
"""

from typing import Any

from dexterhouse.apps.projects.models import Artifact, ArtifactKind, Project
from dexterhouse.apps.workflows.models import PhaseRun

TEAM_FIELDS = (
    "name",
    "version",
    "role",
    "reason",
    "for_tasks",
    "permissions",
    "risk",
    "verified",
    "rating",
    "installs",
    "author_github",
)


def latest(project: Project) -> Artifact | None:
    return (
        Artifact.objects.filter(project=project, kind=ArtifactKind.TEAM_PROPOSAL)
        .order_by("-created_at")
        .first()
    )


def proposals(project: Project) -> list[dict[str, Any]]:
    artifact = latest(project)
    return list(artifact.data.get("proposals", [])) if artifact and artifact.data else []


def gate_team(row: PhaseRun) -> dict[str, Any] | None:
    """The team proposal produced in this phase run, for the gate payload (or None)."""
    artifact = (
        Artifact.objects.filter(phase_run=row, kind=ArtifactKind.TEAM_PROPOSAL)
        .order_by("-created_at")
        .first()
    )
    if artifact is None or not artifact.data:
        return None
    data = artifact.data
    return {
        "artifact_id": str(artifact.id),
        "marketplace_status": data.get("marketplace_status"),
        "summary": data.get("summary", ""),
        "proposals": [{k: p.get(k) for k in TEAM_FIELDS} for p in data.get("proposals", [])],
        "installed": list(data.get("installed", [])),
    }


def installs_without_gate(proposal: dict[str, Any]) -> bool:
    """Whether an automatic approval may install it: verified and low risk in the index."""
    from dexterhouse.apps.packages.services.marketplace import entry

    found = entry(str(proposal.get("name", "")))
    return found is not None and found.verified and found.risk == "low"
