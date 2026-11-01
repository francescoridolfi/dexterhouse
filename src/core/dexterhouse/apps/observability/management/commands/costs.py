# SPDX-License-Identifier: AGPL-3.0-or-later
"""`manage.py costs rollup [--months 6]` and `costs refresh` (recompute spend)."""

from django.core.management.base import BaseCommand, CommandParser

from dexterhouse.apps.observability.services import budget, rollup
from dexterhouse.apps.projects.models import Project


class Command(BaseCommand):
    help = "Cost maintenance: roll up old LLM calls, recompute project and organization spend."

    def add_arguments(self, parser: CommandParser) -> None:
        sub = parser.add_subparsers(dest="action", required=True)
        up = sub.add_parser("rollup", help="aggregate LLMCall rows into llm_usage_daily")
        up.add_argument("--months", type=int, default=rollup.ROLLUP_AFTER_MONTHS)
        sub.add_parser("refresh", help="recompute Project.spent and Organization.spent_month")

    def handle(self, *args: object, **options: object) -> None:
        if options["action"] == "rollup":
            deleted = rollup.rollup(rollup.cutoff(months=int(options["months"])))  # type: ignore[arg-type]
            self.stdout.write(f"rolled up {deleted} calls")
            return
        count = 0
        for org_id, project_id in Project.objects.values_list("organization_id", "id"):
            budget.record_spend(org_id, project_id)
            count += 1
        self.stdout.write(f"refreshed {count} projects")
