# SPDX-License-Identifier: AGPL-3.0-or-later
"""Install a package (state_machines/package.md): fetch, verify, consent, register.

`request_install` records a `PackageInstall` (the API's `install_id`); `run_install` runs
it: download (git tag, local folder), sha256 against the registry index when the package
is listed there, `dexterhouse-schema` validation, `compat.core`, name and role checks,
then `awaiting_consent` for `risk: high` permissions not confirmed up front, else
`installed`. An upgrade is a new `PackageVersion` that becomes the enabled one; the
previous one stays until no active project uses it (`lifecycle.collect_unused`).
"""

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
import yaml
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from dexterhouse.apps.accounts.models import Organization, User
from dexterhouse.apps.packages.models import (
    InstallStatus,
    Package,
    PackageInstall,
    PackageSource,
    PackageStatus,
    PackageVersion,
    RejectReason,
    VersionStatus,
)
from dexterhouse.apps.packages.services import catalog, store
from dexterhouse.apps.packages.services import index as registry
from dexterhouse.apps.packages.services.events import emit
from dexterhouse.common.errors import InvalidTransitionError, ValidationFailedError
from dexterhouse_schema import SUPPORTED_SCHEMAS, Agent, Manifest, Tool, validate_package
from dexterhouse_schema.manifest import DEFINITION_FILES
from dexterhouse_schema.report import ValidationReport

logger = structlog.get_logger(__name__)


def core_version() -> str:
    """The running core version `compat.core` is checked against."""
    from dexterhouse import __version__

    return __version__


#: Sources copied from a folder: re-installing the same version replaces its files.
FOLDER_SOURCES = (PackageSource.LOCAL, PackageSource.BUILTIN)


class RejectedError(Exception):
    def __init__(self, reason: str, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.reason = reason
        self.errors = errors


@dataclass
class Fetched:
    path: Path
    sha256: str
    git_ref: str = ""
    git_url: str = ""
    warnings: list[str] = field(default_factory=list)


# --- request ---------------------------------------------------------------------------


def classify(source: str) -> str:
    """`marketplace` for `git+…` and registry names, `local` for a path."""
    if source.startswith("git+"):
        store.parse_git_source(source)  # raises FetchError on a malformed source
        return PackageSource.MARKETPLACE
    if source.startswith(("/", ".", "~")) or "/" in source:
        if not settings.PACKAGES_ALLOW_LOCAL:
            raise ValidationFailedError(
                "local sources are disabled (PACKAGES_ALLOW_LOCAL)",
                [{"field": "source", "message": "local paths are for development only"}],
            )
        return PackageSource.LOCAL
    return PackageSource.MARKETPLACE


def request_install(
    *,
    organization: Organization | None,
    source: str,
    version: str = "",
    user: User | None = None,
    project: Any = None,
    confirm_permissions: list[str] | tuple[str, ...] = (),
    builtin: bool = False,
) -> PackageInstall:
    """Record an install request; `source` is `git+https://…@tag`, a path or a registry name.

    `builtin` (only `sync_builtin`) installs a `BUILTIN_DIR` folder as a trusted global
    package. Raises ValidationFailedError for a malformed source; nothing is fetched yet.
    """
    try:
        kind = PackageSource.BUILTIN if builtin else classify(source)
    except store.FetchError as exc:
        raise ValidationFailedError(str(exc), [{"field": "source", "message": str(exc)}]) from exc
    if kind != PackageSource.MARKETPLACE:
        source = str(Path(source).expanduser().resolve())
    return PackageInstall.objects.create(
        organization=organization,
        project=project,
        requested_by=user,
        source=kind,
        source_url=source,
        requested_version=version or "",
        confirm_permissions=sorted(set(confirm_permissions)),
    )


def install(**kwargs: Any) -> PackageInstall:
    """`request_install` + `run_install` in the caller's process (CLI, system actions)."""
    return run_install(request_install(**kwargs).id)


# --- pipeline --------------------------------------------------------------------------


def run_install(install_id: uuid.UUID) -> PackageInstall:
    """Run a recorded install; idempotent once the install left `downloading`."""
    install = PackageInstall.objects.select_related("organization", "requested_by").get(
        id=install_id
    )
    if install.status != InstallStatus.DOWNLOADING:
        return install
    staging = store.staging_dir()
    try:
        fetched = _fetch(install, staging / "pkg")
        _set(install, status=InstallStatus.VERIFYING)
        manifest, report = _verify(install, fetched)
        return _register(install, fetched, manifest, report)
    except RejectedError as exc:
        return _reject(install, exc.reason, exc.errors)
    except registry.IndexUnavailableError as exc:  # fail closed: no index, no hash check
        return _reject(install, RejectReason.FETCH, [str(exc)])
    finally:
        store.discard(staging)


def _set(install: PackageInstall, **fields: Any) -> None:
    for key, value in fields.items():
        setattr(install, key, value)
    install.save(update_fields=[*fields, "updated_at"])


def _event(install: PackageInstall, event_type: str, payload: dict[str, Any]) -> None:
    emit(
        event_type,
        payload,
        organization_id=install.organization_id,
        project_id=install.project_id,
        user=install.requested_by,
    )


def _installing(install: PackageInstall) -> None:
    _event(
        install,
        "package.installing",
        {
            "install_id": install.id,
            "name": install.name,
            "version": install.version,
            "kind": install.kind,
            "source": install.source,
        },
    )


def _clone_url(url: str) -> str:
    """The URL to clone: the first `PACKAGES_GIT_MIRRORS` prefix that matches is replaced.

    The hash is still checked against the index entry of the original URL.
    """
    for prefix, mirror in settings.PACKAGES_GIT_MIRRORS.items():
        if url.startswith(prefix):
            return mirror + url.removeprefix(prefix)
    return url


def _fetch(install: PackageInstall, dest: Path) -> Fetched:
    try:
        if install.source in FOLDER_SOURCES:
            return Fetched(dest, store.copy_folder(Path(install.source_url), dest))
        if install.source_url.startswith("git+"):
            git = store.parse_git_source(install.source_url)
        else:
            git = _resolve_marketplace(install)
        sha = store.fetch_git(store.GitSource(_clone_url(git.url), git.ref), dest)
        return Fetched(dest, sha, git_ref=git.ref, git_url=git.url)
    except (store.FetchError, registry.IndexUnavailableError) as exc:
        raise RejectedError(RejectReason.FETCH, [str(exc)]) from exc


def _resolve_marketplace(install: PackageInstall) -> store.GitSource:
    """A registry name: repository and tag of the requested (or latest compatible) version."""
    snapshot = registry.get_index()
    if snapshot is None:
        raise store.FetchError("no registry configured (REGISTRY_INDEX_URL)")
    entry = snapshot.get(install.source_url)
    if entry is None:
        raise store.FetchError(f"{install.source_url} is not in the registry index")
    chosen = registry.pick_version(entry, install.requested_version or None)
    if chosen is None:
        wanted = install.requested_version or f"a version compatible with core {core_version()}"
        raise store.FetchError(f"{entry.name}: {wanted} not in the registry index")
    _set(install, name=entry.name, version=chosen.version, kind=entry.kind)
    _installing(install)
    return store.GitSource(entry.repo, chosen.ref)


def _read_manifest(root: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load((root / "dexterhouse.yaml").read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeDecodeError) as exc:
        raise RejectedError(RejectReason.SCHEMA, [f"dexterhouse.yaml: {exc}"]) from exc
    if not isinstance(data, dict):
        raise RejectedError(RejectReason.SCHEMA, ["dexterhouse.yaml: top level must be a mapping"])
    return data


def _check_schema_versions(root: Path, raw: dict[str, Any]) -> None:
    """CD-019: a `schema:` this core does not support makes the package incompatible."""
    files = {"dexterhouse.yaml": raw}
    definition = DEFINITION_FILES.get(str(raw.get("kind")))
    if definition and (root / definition).is_file():
        try:
            files[definition] = yaml.safe_load((root / definition).read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError, UnicodeDecodeError):
            return  # reported by the validator
    for name, data in files.items():
        value = data.get("schema") if isinstance(data, dict) else None
        if isinstance(value, int) and value not in SUPPORTED_SCHEMAS:
            supported = ", ".join(map(str, sorted(SUPPORTED_SCHEMAS)))
            raise RejectedError(
                RejectReason.COMPAT,
                [f"{name}: schema {value} is not supported by this core (supported: {supported})"],
            )


def _verify(install: PackageInstall, fetched: Fetched) -> tuple[Manifest, ValidationReport]:
    raw = _read_manifest(fetched.path)
    known = bool(install.name)
    if not known:
        _set(
            install,
            name=str(raw.get("name", ""))[:120],
            version=str(raw.get("version", ""))[:32],
            kind=raw.get("kind") if raw.get("kind") in DEFINITION_FILES else "",
        )
        if install.kind:
            _installing(install)
    _check_schema_versions(fetched.path, raw)
    report = validate_package(fetched.path)
    if not report.ok:
        scan = all(e.message.startswith("forbidden pattern") for e in report.errors)
        reason = RejectReason.SCAN if scan else RejectReason.SCHEMA
        raise RejectedError(reason, [str(e) for e in report.errors])
    manifest = report.models["dexterhouse.yaml"]
    assert isinstance(manifest, Manifest)  # nosec B101: validated just above
    if (install.name, install.version) != (manifest.name, manifest.version):
        raise RejectedError(
            RejectReason.SCHEMA,
            [
                f"package is {manifest.name}@{manifest.version}, the registry lists "
                f"{install.name}@{install.version}"
            ],
        )
    if fetched.git_url:
        fetched.warnings.extend(_check_index(manifest, fetched))
    if not registry.compatible(manifest.compat.core, core_version()):
        raise RejectedError(
            RejectReason.COMPAT,
            [f"compat.core {manifest.compat.core!r} does not include core {core_version()}"],
        )
    _check_names(install, manifest, report)
    return manifest, report


def _check_index(manifest: Manifest, fetched: Fetched) -> list[str]:
    """sha256 against the registry index when the package is listed there (T17)."""
    snapshot = registry.get_index()  # IndexUnavailableError: fail closed
    if snapshot is None:
        return ["no registry configured: sha256 not verified"]
    entry = snapshot.get(manifest.name)
    if entry is None:
        return [f"{manifest.name} is not in the registry index: sha256 not verified"]
    if not registry.same_repo(entry.repo, fetched.git_url):
        raise RejectedError(
            RejectReason.HASH,
            [f"{manifest.name} is registered with {entry.repo}, not {fetched.git_url}"],
        )
    listed = next((v for v in entry.versions if v.version == manifest.version), None)
    if listed is None:
        raise RejectedError(
            RejectReason.HASH, [f"{manifest.name}@{manifest.version} is not in the registry index"]
        )
    if listed.ref != fetched.git_ref:
        raise RejectedError(
            RejectReason.HASH,
            [f"the registry lists {manifest.version} at ref {listed.ref}, not {fetched.git_ref}"],
        )
    if listed.sha256 != fetched.sha256:
        raise RejectedError(
            RejectReason.HASH,
            [f"sha256 mismatch: the registry lists {listed.sha256}, the tag has {fetched.sha256}"],
        )
    return []


def _check_names(install: PackageInstall, manifest: Manifest, report: ValidationReport) -> None:
    """One live package per name in a scope; one enabled agent package per role."""
    org_id = install.organization_id
    clash = Package.objects.filter(name=manifest.name, deleted_at__isnull=True).exclude(
        organization_id=org_id
    )
    if org_id:
        clash = clash.filter(organization__isnull=True)
    if clash.exists():
        raise RejectedError(RejectReason.SCHEMA, [f"{manifest.name} is already installed globally"])
    same = Package.objects.filter(
        organization_id=org_id, name=manifest.name, deleted_at__isnull=True
    ).first()
    if same and same.kind != manifest.kind:
        raise RejectedError(
            RejectReason.SCHEMA, [f"{manifest.name} is already installed as a {same.kind}"]
        )
    builtin = install.source == PackageSource.BUILTIN
    if same and (same.source == PackageSource.BUILTIN) != builtin:
        detail = "a built-in package" if not builtin else f"installed from {same.source}"
        raise RejectedError(RejectReason.SCHEMA, [f"{manifest.name} is {detail}"])
    agent = report.models.get("agent.yaml")
    if isinstance(agent, Agent):
        holder = role_holder(agent.role, org_id, exclude_name=manifest.name)
        if holder:
            raise RejectedError(
                RejectReason.SCHEMA,
                [f"role {agent.role} is already provided by the package {holder}"],
            )


def role_holder(role: str, organization_id: uuid.UUID | None, exclude_name: str = "") -> str:
    """Name of another enabled agent package with `role` in this scope, if any."""
    # A global package is seen by every organization: it must not clash with any of them.
    scope = catalog.visible(organization_id) if organization_id else Q()
    for version in PackageVersion.objects.select_related("package").filter(
        package__in=Package.objects.filter(scope, kind="agent", deleted_at__isnull=True),
        status=VersionStatus.INSTALLED,
    ):
        if (
            version.package.enabled_version_id == version.id
            and version.package.name != exclude_name
            and version.definition.get("role") == role
        ):
            return version.package.name
    return ""


def permissions_of(
    report: ValidationReport, organization_id: uuid.UUID | None
) -> list[dict[str, Any]]:
    """A tool's permissions, or the tools an agent requires with their risk (if known)."""
    tool = report.models.get("tool.yaml")
    if isinstance(tool, Tool):
        return [
            {"id": p.id, "risk": p.risk, "description": p.description or ""}
            for p in tool.permissions
        ]
    agent = report.models.get("agent.yaml")
    if not isinstance(agent, Agent):
        return []
    known = {
        p["id"]: p
        for v in catalog.enabled_versions("tool", organization_id, ensure=False)
        for p in v.permissions
    }
    return [
        known.get(tool_id, {"id": tool_id, "risk": None, "description": ""})
        for tool_id in agent.tools
    ]


def _register(
    install: PackageInstall, fetched: Fetched, manifest: Manifest, report: ValidationReport
) -> PackageInstall:
    permissions = permissions_of(report, install.organization_id)
    high = [p for p in permissions if p["risk"] == "high"]
    trusted = install.source == PackageSource.BUILTIN
    pending = [p for p in high if p["id"] not in install.confirm_permissions and not trusted]
    definition = report.models[manifest.definition_file]
    target = store.install_path(install.organization_id, manifest.name, manifest.version)
    with transaction.atomic():
        package = _package_for(install, manifest)
        version = package.versions.filter(version=manifest.version).first()
        if version and version.status != VersionStatus.REMOVED:
            if version.sha256 == fetched.sha256 and Path(version.install_path).is_dir():
                return _already_installed(install, version)
            if install.source not in FOLDER_SOURCES:  # published versions are immutable
                raise RejectedError(
                    RejectReason.HASH,
                    [f"{manifest.name}@{manifest.version} is installed with another content"],
                )
        store.place(fetched.path, target)
        version = version or PackageVersion(package=package, version=manifest.version)
        version.git_ref = fetched.git_ref
        version.sha256 = fetched.sha256
        version.manifest = manifest.model_dump(mode="json", by_alias=True, exclude_none=True)
        version.definition = definition.model_dump(mode="json", by_alias=True, exclude_none=True)
        version.schema = manifest.schema_version
        version.compat_core = manifest.compat.core
        version.permissions = permissions
        version.install_path = str(target)
        version.status_reason = ""
        version.status = VersionStatus.AWAITING_CONSENT if pending else VersionStatus.INSTALLED
        if high and not pending:
            version.consent_by = install.requested_by
            version.consent_at = timezone.now()
        version.save()
        _set(
            install,
            package_version=version,
            warnings=fetched.warnings,
            consent_required=pending,
        )
        if pending:
            if package.enabled_version_id is None:
                _package_status(package, PackageStatus.AWAITING_CONSENT)
            _set(install, status=InstallStatus.AWAITING_CONSENT)
            _event(
                install,
                "package.consent_requested",
                {"install_id": install.id, "name": package.name, "permissions": pending},
            )
            return install
        return _activate(install, version)


def _package_for(install: PackageInstall, manifest: Manifest) -> Package:
    package = (
        Package.objects.select_for_update()
        .filter(
            organization_id=install.organization_id, name=manifest.name, deleted_at__isnull=True
        )
        .first()
    )
    if package is None:
        package = Package.objects.create(
            organization_id=install.organization_id,
            name=manifest.name,
            kind=manifest.kind,
            source=install.source,
            source_url=install.source_url,
            status=PackageStatus.AWAITING_CONSENT,
        )
    elif (package.source, package.source_url) != (install.source, install.source_url):
        package.source, package.source_url = install.source, install.source_url
        package.save(update_fields=["source", "source_url", "updated_at"])
    return package


def _package_status(package: Package, status: str, reason: str = "") -> None:
    package.status, package.status_reason = status, reason
    package.save(update_fields=["status", "status_reason", "updated_at"])


def _already_installed(install: PackageInstall, version: PackageVersion) -> PackageInstall:
    status = (
        InstallStatus.AWAITING_CONSENT
        if version.status == VersionStatus.AWAITING_CONSENT
        else InstallStatus.INSTALLED
    )
    _set(install, status=status, package_version=version, finished_at=timezone.now())
    return install


def _activate(install: PackageInstall, version: PackageVersion) -> PackageInstall:
    """Make `version` the enabled one (`package.installed`); superseded ones are collected."""
    from dexterhouse.apps.packages.services.lifecycle import collect_unused

    package = version.package
    package.enabled_version = version
    package.deleted_at = None
    package.status, package.status_reason = PackageStatus.INSTALLED, ""
    package.save(
        update_fields=["enabled_version", "deleted_at", "status", "status_reason", "updated_at"]
    )
    _set(install, status=InstallStatus.INSTALLED, finished_at=timezone.now())
    roles = [version.definition["role"]] if package.kind == "agent" else []
    _event(
        install,
        "package.installed",
        {
            "package_id": package.id,
            "version_id": version.id,
            "name": package.name,
            "version": version.version,
            "kind": package.kind,
            "roles": roles,
        },
    )
    logger.info(
        "packages.installed", name=package.name, version=version.version, source=package.source
    )
    transaction.on_commit(lambda: collect_unused(package.id))
    return install


def _reject(install: PackageInstall, reason: str, errors: list[str]) -> PackageInstall:
    status = InstallStatus.FAILED if reason == RejectReason.FETCH else InstallStatus.INCOMPATIBLE
    _set(install, status=status, reason=reason, errors=errors, finished_at=timezone.now())
    _event(
        install,
        "package.rejected",
        {
            "install_id": install.id,
            "name": install.name or install.source_url[:120],
            "reason": reason,
            "errors": errors,
        },
    )
    logger.warning("packages.rejected", source=install.source_url, reason=reason, errors=errors)
    return install


# --- consent ---------------------------------------------------------------------------


def consent(install_id: uuid.UUID, *, user: User | None, accept: bool) -> PackageInstall:
    """Accept or decline the `risk: high` permissions of an install awaiting consent."""
    with transaction.atomic():
        install = PackageInstall.objects.select_for_update().get(id=install_id)
        if install.status != InstallStatus.AWAITING_CONSENT or install.package_version is None:
            raise InvalidTransitionError(f"install is {install.status}, not awaiting_consent")
        version = install.package_version
        if accept:
            version.status = VersionStatus.INSTALLED
            version.consent_by, version.consent_at = user, timezone.now()
            version.save(update_fields=["status", "consent_by", "consent_at", "updated_at"])
            return _activate(install, version)
        version.status = VersionStatus.REMOVED
        version.status_reason = "consent declined"
        version.save(update_fields=["status", "status_reason", "updated_at"])
        package = version.package
        if not package.versions.exclude(status=VersionStatus.REMOVED).exists():
            package.deleted_at = timezone.now()
            _package_status(package, PackageStatus.REMOVED, "consent declined")
            package.save(update_fields=["deleted_at"])
        path = version.install_path
        transaction.on_commit(lambda: store.discard(path))
        _set(
            install,
            status=InstallStatus.DECLINED,
            reason=RejectReason.DECLINED,
            errors=["the high-risk permissions were declined"],
            finished_at=timezone.now(),
        )
        _event(
            install,
            "package.rejected",
            {
                "install_id": install.id,
                "name": package.name,
                "reason": RejectReason.DECLINED,
                "errors": install.errors,
            },
        )
    return install
