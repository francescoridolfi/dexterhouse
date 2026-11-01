# SPDX-License-Identifier: AGPL-3.0-or-later
"""REST v1 for installed packages (contracts/api/agents_packages.md, "Packages").

Reading is for every member of the organization; installing, consenting, enabling,
disabling and removing need `admin` (tokens: scope `packages:manage`). Global packages
(built-in, or installed by an operator with the CLI) are listed but managed only by the
CLI: the API answers 403 for them.
"""

import tarfile
import tempfile
import uuid
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import exceptions, serializers, status
from rest_framework.request import Request
from rest_framework.response import Response

from dexterhouse.apps.accounts.models import Role, Scope
from dexterhouse.apps.packages.models import Package, PackageInstall, PackageVersion, VersionStatus
from dexterhouse.apps.packages.services import catalog, installer, lifecycle, store
from dexterhouse.common.api import ApiView, OrgContext
from dexterhouse.common.errors import ValidationFailedError
from dexterhouse_schema import validate_package

READ = (Role.VIEWER, Scope.PROJECTS_READ)
VALIDATE = (Role.MEMBER, Scope.PROJECTS_READ)
MANAGE = (Role.ADMIN, Scope.PACKAGES_MANAGE)


def _ts(value: Any) -> str | None:
    return value.isoformat() if value else None


def version_json(version: PackageVersion, *, detail: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": str(version.id),
        "version": version.version,
        "status": version.status,
        "status_reason": version.status_reason,
        "git_ref": version.git_ref,
        "sha256": version.sha256,
        "compat_core": version.compat_core,
        "schema": version.schema,
        "consent_by": str(version.consent_by_id) if version.consent_by_id else None,
        "consent_at": _ts(version.consent_at),
        "created_at": _ts(version.created_at),
    }
    if detail:
        data["manifest"] = version.manifest
        data["definition"] = version.definition
        data["permissions"] = version.permissions
    return data


def package_json(package: Package, *, detail: bool = False) -> dict[str, Any]:
    enabled = package.enabled_version
    data: dict[str, Any] = {
        "id": str(package.id),
        "name": package.name,
        "kind": package.kind,
        "source": package.source,
        "source_url": package.source_url,
        "status": package.status,
        "status_reason": package.status_reason,
        "global": package.organization_id is None,
        "version": enabled.version if enabled else None,
        "description": (enabled.manifest.get("description") if enabled else None),
        "role": enabled.definition.get("role") if enabled and package.kind == "agent" else None,
        "risk": _risk(enabled),
        "latest_available": package.latest_available or None,
        "created_at": _ts(package.created_at),
        "updated_at": _ts(package.updated_at),
    }
    if detail:
        versions = package.versions.exclude(status=VersionStatus.REMOVED).order_by("-created_at")
        data["versions"] = [version_json(v, detail=True) for v in versions]
        data["permissions"] = enabled.permissions if enabled else []
        data["projects"] = [str(p) for p in catalog.projects_using_package(package)]
    return data


def _risk(version: PackageVersion | None) -> str | None:
    if version is None:
        return None
    risks = {p.get("risk") for p in version.permissions}
    return next((r for r in ("high", "medium", "low") if r in risks), "low")


def install_json(install: PackageInstall) -> dict[str, Any]:
    version = install.package_version
    return {
        "install_id": str(install.id),
        "status": install.status,
        "source": install.source,
        "source_url": install.source_url,
        "name": install.name or None,
        "version": install.version or None,
        "kind": install.kind or None,
        "reason": install.reason or None,
        "errors": install.errors,
        "warnings": install.warnings,
        "consent_required": {"permissions": install.consent_required}
        if install.consent_required and install.status == "awaiting_consent"
        else None,
        "package": str(version.package_id) if version else None,
        "package_version": str(version.id) if version else None,
        "project": str(install.project_id) if install.project_id else None,
        "created_at": _ts(install.created_at),
        "finished_at": _ts(install.finished_at),
    }


def _packages(ctx: OrgContext):  # type: ignore[no-untyped-def]
    return (
        Package.objects.filter(catalog.visible(ctx.organization.id), deleted_at__isnull=True)
        .select_related("enabled_version")
        .order_by("-created_at")
    )


def _managed(ctx: OrgContext, package_id: uuid.UUID) -> Package:
    package = get_object_or_404(_packages(ctx), pk=package_id)
    if package.organization_id is None:
        raise exceptions.PermissionDenied(
            "global packages are managed with the CLI (dexterhouse pkg)"
        )
    return package


class InstallInput(serializers.Serializer):
    source = serializers.CharField(required=False, max_length=500)
    marketplace = serializers.CharField(required=False, max_length=120)
    version = serializers.CharField(required=False, allow_blank=True, max_length=32)
    confirm_permissions = serializers.ListField(
        child=serializers.CharField(max_length=120), required=False, default=list
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if bool(attrs.get("source")) == bool(attrs.get("marketplace")):
            raise serializers.ValidationError("give exactly one of `source` or `marketplace`")
        if attrs.get("marketplace") and attrs["marketplace"].startswith("git+"):
            raise serializers.ValidationError({"marketplace": "a registry name, not a URL"})
        return attrs


class PackageListView(ApiView):
    def get(self, request: Request) -> Response:
        ctx = self.require(*READ)
        rows = _packages(ctx)
        for field in ("kind", "source", "status"):
            if value := request.query_params.get(field):
                rows = rows.filter(**{field: value})
        return self.paginate(rows, package_json)

    def post(self, request: Request) -> Response:
        ctx = self.require(*MANAGE)
        body = InstallInput(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        if data.get("marketplace") is not None and "/" in data["marketplace"]:
            raise ValidationFailedError(
                "invalid package name", [{"field": "marketplace", "message": "not a name"}]
            )
        install = installer.request_install(
            organization=ctx.organization,
            source=data.get("source") or data["marketplace"],
            version=data.get("version") or "",
            user=ctx.user,
            confirm_permissions=data["confirm_permissions"],
        )
        from dexterhouse.apps.packages.tasks import run_install

        transaction.on_commit(lambda: run_install.delay(str(install.id)))
        return Response(
            {"install_id": str(install.id), "status": install.status},
            status=status.HTTP_202_ACCEPTED,
        )


class PackageDetailView(ApiView):
    def get(self, request: Request, package_id: uuid.UUID) -> Response:
        package = get_object_or_404(_packages(self.require(*READ)), pk=package_id)
        return Response(package_json(package, detail=True))

    def delete(self, request: Request, package_id: uuid.UUID) -> Response:
        ctx = self.require(*MANAGE)
        lifecycle.remove(_managed(ctx, package_id), user=ctx.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PackageEnableView(ApiView):
    def post(self, request: Request, package_id: uuid.UUID) -> Response:
        ctx = self.require(*MANAGE)
        package = lifecycle.enable(_managed(ctx, package_id), user=ctx.user)
        return Response(package_json(package))


class PackageDisableView(ApiView):
    def post(self, request: Request, package_id: uuid.UUID) -> Response:
        ctx = self.require(*MANAGE)
        reason = str(request.data.get("reason") or "")[:200] or None
        package = lifecycle.disable(_managed(ctx, package_id), user=ctx.user, reason=reason)
        return Response(package_json(package))


def _install(ctx: OrgContext, install_id: uuid.UUID) -> PackageInstall:
    rows = PackageInstall.objects.filter(organization=ctx.organization)
    return get_object_or_404(rows.select_related("package_version"), pk=install_id)


class InstallDetailView(ApiView):
    def get(self, request: Request, install_id: uuid.UUID) -> Response:
        return Response(install_json(_install(self.require(*READ), install_id)))


class ConsentInput(serializers.Serializer):
    accept = serializers.BooleanField()


class InstallConsentView(ApiView):
    def post(self, request: Request, install_id: uuid.UUID) -> Response:
        ctx = self.require(*MANAGE)
        install = _install(ctx, install_id)
        body = ConsentInput(data=request.data)
        body.is_valid(raise_exception=True)
        install = installer.consent(install.id, user=ctx.user, accept=body.validated_data["accept"])
        return Response(install_json(install))


class ValidateView(ApiView):
    """`{path}` (local sources enabled only) or a multipart `archive` (tar, tar.gz)."""

    def post(self, request: Request) -> Response:
        self.require(*VALIDATE)
        upload = request.FILES.get("archive")
        if upload is not None:
            if upload.size > store.MAX_PACKAGE_BYTES:
                raise ValidationFailedError(
                    "archive too large", [{"field": "archive", "message": "limit 20 MB"}]
                )
            with tempfile.TemporaryDirectory() as tmp:
                try:
                    store.extract_tar(upload.read(), Path(tmp) / "pkg")
                except (store.FetchError, tarfile.TarError) as exc:
                    raise ValidationFailedError(
                        str(exc), [{"field": "archive", "message": str(exc)}]
                    ) from exc
                return Response(_report(_package_root(Path(tmp) / "pkg")))
        path = str(request.data.get("path") or "")
        if not path or not settings.PACKAGES_ALLOW_LOCAL:
            raise ValidationFailedError(
                "give a multipart `archive` (or `path`, when local sources are enabled)",
                [{"field": "archive", "message": "required"}],
            )
        return Response(_report(Path(path)))


def _package_root(root: Path) -> Path:
    """The folder holding `dexterhouse.yaml` (archives often wrap it in one directory)."""
    if (root / "dexterhouse.yaml").is_file():
        return root
    children = [p for p in root.iterdir() if p.is_dir()] if root.is_dir() else []
    return children[0] if len(children) == 1 else root


def _report(root: Path) -> dict[str, Any]:
    report = validate_package(root)
    return {
        "valid": report.ok,
        "errors": [{"path": i.path, "loc": i.loc, "message": i.message} for i in report.errors],
        "warnings": [{"path": i.path, "loc": i.loc, "message": i.message} for i in report.warnings],
    }
