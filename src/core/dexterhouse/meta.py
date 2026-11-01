# SPDX-License-Identifier: AGPL-3.0-or-later
"""`GET /api/v1/meta`: what this installation offers (admin.md); the SPA adapts to it."""

from rest_framework.request import Request
from rest_framework.response import Response

from dexterhouse import __version__
from dexterhouse.apps.accounts.models import Role, Scope
from dexterhouse.apps.gateway.providers import PROVIDERS
from dexterhouse.apps.workflows.registry import installed_processes
from dexterhouse.common.api import ApiView

#: API areas not implemented yet; the SPA shows "coming soon" for them.
FEATURES = {
    "packages": True,  # E-07: installed packages API
    "marketplace": False,  # E-11
    "office_3d": False,  # E-09
    "organization_ws": False,
    "model_profile_test": False,
    "api_tokens": False,
}


class MetaView(ApiView):
    def get(self, request: Request) -> Response:
        ctx = self.require(Role.VIEWER, Scope.PROJECTS_READ)
        processes = installed_processes(ctx.organization.id)
        return Response(
            {
                "version": __version__,
                "schema": [1],
                "providers": sorted(PROVIDERS),
                "processes": [
                    {
                        "name": p.name,
                        "version": p.version,
                        "phases": [{"id": ph.id, "agent": ph.agent} for ph in p.process.phases],
                        "requirements": p.requirements,
                    }
                    for p in sorted(processes.values(), key=lambda p: p.name)
                ],
                "3d_enabled": FEATURES["office_3d"],
                "features": FEATURES,
            }
        )
