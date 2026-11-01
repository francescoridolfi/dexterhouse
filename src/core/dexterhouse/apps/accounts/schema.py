# SPDX-License-Identifier: AGPL-3.0-or-later
"""OpenAPI security scheme of `ApiTokenAuthentication` (drf-spectacular extension)."""

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class ApiTokenScheme(OpenApiAuthenticationExtension):
    target_class = "dexterhouse.apps.accounts.authentication.ApiTokenAuthentication"
    name = "bearerToken"

    def get_security_definition(self, auto_schema: object) -> dict[str, str]:
        return {
            "type": "http",
            "scheme": "bearer",
            "description": "API token with scopes (`dexterhouse token create`, docs/api.md).",
        }
