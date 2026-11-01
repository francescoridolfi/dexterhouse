# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read side: the installed packages an organization sees, and who uses a version.

An organization sees the global packages (built-in first) plus its own. Only a package's
*enabled* version is offered to new hires, the tool catalog and new projects; a version
already pinned by an active project (`AgentInstance.package_version`, the project's
`process_version`) stays readable until the project ends.
"""

import uuid

from django.db.models import Case, F, IntegerField, Q, QuerySet, Value, When

from dexterhouse.apps.packages.models import (
    Package,
    PackageSource,
    PackageVersion,
    VersionStatus,
)

ACTIVE_PROJECT_STATUSES = ("running", "waiting", "paused")


def visible(organization_id: uuid.UUID | None) -> Q:
    """Packages an organization sees (global ones only when `organization_id` is None)."""
    scope = Q(organization__isnull=True)
    return scope | Q(organization_id=organization_id) if organization_id else scope


def visible_packages(organization_id: uuid.UUID | None) -> QuerySet[Package]:
    return Package.objects.filter(visible(organization_id), deleted_at__isnull=True)


def _builtin_first(queryset: QuerySet[PackageVersion]) -> QuerySet[PackageVersion]:
    order = Case(
        When(package__source=PackageSource.BUILTIN, then=Value(0)),
        default=Value(1),
        output_field=IntegerField(),
    )
    return queryset.annotate(_builtin=order).order_by("_builtin", "package__name")


def enabled_versions(
    kind: str, organization_id: uuid.UUID | None = None, *, ensure: bool = True
) -> list[PackageVersion]:
    """The enabled version of every package of `kind` the organization sees.

    `ensure` syncs the built-ins first when the database has none (see `ensure_builtin`).
    """
    if ensure:
        from dexterhouse.apps.packages.services.builtin import ensure_builtin

        ensure_builtin()
    rows = PackageVersion.objects.select_related("package").filter(
        package__in=visible_packages(organization_id).filter(kind=kind),
        package__enabled_version=F("id"),
        status=VersionStatus.INSTALLED,
    )
    return list(_builtin_first(rows))


def find_version(
    kind: str,
    name: str,
    organization_id: uuid.UUID | None = None,
    version: str | None = None,
) -> PackageVersion | None:
    """The enabled version of package `name`, or exactly `version` while it is installed.

    With `version`, a superseded or disabled version is still returned (projects pinned to
    it keep working); a removed one is not.
    """
    if version is None:
        return next(
            (v for v in enabled_versions(kind, organization_id) if v.package.name == name), None
        )
    rows = PackageVersion.objects.select_related("package").filter(
        package__in=visible_packages(organization_id).filter(kind=kind, name=name),
        version=version,
        status__in=(VersionStatus.INSTALLED, VersionStatus.DISABLED),
    )
    return _builtin_first(rows).first()


def projects_using(version: PackageVersion) -> list[uuid.UUID]:
    """Active projects pinned to this agent or process version (tools are not pinned)."""
    from dexterhouse.apps.agents.models import AgentInstance, AgentStatus
    from dexterhouse.apps.projects.models import Project

    package = version.package
    if package.kind == "agent":
        rows = AgentInstance.objects.filter(
            installed_version=version, project__status__in=ACTIVE_PROJECT_STATUSES
        ).exclude(status=AgentStatus.RELEASED)
        return sorted(set(rows.values_list("project_id", flat=True)))
    if package.kind == "process":
        projects = Project.objects.filter(
            process_name=package.name,
            process_version=version.version,
            status__in=ACTIVE_PROJECT_STATUSES,
        )
        if package.organization_id:
            projects = projects.filter(organization_id=package.organization_id)
        return sorted(projects.values_list("id", flat=True))
    return []


def projects_using_package(package: Package) -> list[uuid.UUID]:
    """Active projects that would break if the package disappeared."""
    from dexterhouse.apps.agents.models import AgentInstance, AgentStatus

    if package.kind != "tool":
        found: set[uuid.UUID] = set()
        for version in package.versions.exclude(status=VersionStatus.REMOVED):
            found.update(projects_using(version))
        return sorted(found)
    permissions = [
        p["id"]
        for v in package.versions.exclude(status=VersionStatus.REMOVED)
        for p in v.permissions
    ]
    agents = AgentInstance.objects.filter(
        allowed_tools__overlap=permissions or ["-"],
        project__status__in=ACTIVE_PROJECT_STATUSES,
    ).exclude(status=AgentStatus.RELEASED)
    if package.organization_id:
        agents = agents.filter(organization_id=package.organization_id)
    return sorted(set(agents.values_list("project_id", flat=True)))
