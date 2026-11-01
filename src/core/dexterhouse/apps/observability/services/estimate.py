# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cost estimate before start (F-012, pricing_and_embeddings.md).

Up to `HISTORY_MIN_PROJECTS` completed projects with the same process: a static range per
process for a brief of `REFERENCE_BRIEF_CHARS`, scaled with the brief length. Afterwards:
median and p80 of what those projects spent, corrected for brief length.
"""

from decimal import ROUND_HALF_UP, Decimal
from statistics import median, quantiles
from typing import Any

from dexterhouse.apps.projects.models import Project, ProjectStatus

HISTORY_MIN_PROJECTS = 10
REFERENCE_BRIEF_CHARS = 2_000
#: EUR (low, high) for a brief of REFERENCE_BRIEF_CHARS characters.
STATIC_RANGES: dict[str, tuple[Decimal, Decimal]] = {
    "software-house-default": (Decimal(8), Decimal(25)),
    "code-review-only": (Decimal(1), Decimal(5)),
}
DEFAULT_RANGE = (Decimal(5), Decimal(20))
CENT = Decimal("0.1")


def _scale(brief_chars: int) -> Decimal:
    return max(Decimal(1), Decimal(brief_chars) / REFERENCE_BRIEF_CHARS)


def _round(value: Decimal) -> float:
    return float(value.quantize(CENT, rounding=ROUND_HALF_UP))


def estimate(organization_id: Any, process: str, brief_chars: int) -> dict[str, Any]:
    """`{low, high, basis, currency}` for a brief of `brief_chars` run with `process`."""
    history = list(
        Project.objects.filter(
            organization_id=organization_id,
            process_name=process,
            status__in=(ProjectStatus.COMPLETED, ProjectStatus.ARCHIVED),
            completed_at__isnull=False,
        ).values_list("spent", "brief")
    )
    if len(history) >= HISTORY_MIN_PROJECTS:
        # Normalise each spend to the reference brief length, then scale to this brief.
        normalised = [Decimal(spent) / _scale(len(brief)) for spent, brief in history]
        low = Decimal(median(normalised))
        high = Decimal(quantiles(normalised, n=10)[7])  # p80
        basis = "history"
    else:
        low, high = STATIC_RANGES.get(process, DEFAULT_RANGE)
        basis = "static"
    factor = _scale(brief_chars)
    return {
        "low": _round(low * factor),
        "high": _round(max(high, low) * factor),
        "basis": basis,
        "currency": "EUR",
    }


def estimate_for_project(project: Project) -> dict[str, Any]:
    return estimate(project.organization_id, project.process_name, len(project.brief))
