# SPDX-License-Identifier: AGPL-3.0-or-later
"""`dexterhouse pkg validate|init|install|list|remove|enable|disable`.

`validate` and `init` work on a folder and need nothing else. The other commands run the
installer in-process against the core database, so they run where the core runs (in
compose: `docker compose exec web dexterhouse pkg install …`). Without `--org` they
manage *global* packages, seen by every organization.
"""

import os
import re
import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from dexterhouse.cli import templates

app = typer.Typer(help="Validate, scaffold and install DexterHouse packages.", no_args_is_help=True)

#: Exit codes: 1 invalid / rejected, 2 usage, 3 consent needed but not given.
EXIT_CONSENT = 3


def _echo_issues(report: Any) -> None:
    for warning in report.warnings:
        typer.secho(f"warning: {warning}", err=True, fg="yellow")
    for error in report.errors:
        typer.secho(f"error: {error}", err=True, fg="red")


@app.command()
def validate(
    path: Annotated[Path, typer.Argument(help="Package folder or one package file.")],
) -> None:
    """Validate a package with dexterhouse-schema (what the registry CI runs)."""
    from dexterhouse_schema import validate_path

    report = validate_path(path)
    _echo_issues(report)
    if not report.ok:
        typer.echo(f"{path}: invalid ({len(report.errors)} error(s))", err=True)
        raise typer.Exit(1)
    typer.echo(f"{path}: valid")


@app.command()
def init(
    name: Annotated[str, typer.Argument(help="Package name, e.g. security-reviewer.")],
    kind: Annotated[str, typer.Option("--kind", "-k", help="agent | tool | process")] = "agent",
    directory: Annotated[Path, typer.Option("--dir", help="Where to create the folder.")] = Path(
        "."
    ),
    author: Annotated[str, typer.Option("--author", help="Author name.")] = "Your Name",
) -> None:
    """Create the smallest valid package of `kind` in `<dir>/<name>`."""
    from dexterhouse_schema.common import PACKAGE_NAME_PATTERN

    if kind not in {"agent", "tool", "process"}:
        raise typer.BadParameter("kind must be agent, tool or process", param_hint="--kind")
    if not re.match(PACKAGE_NAME_PATTERN, name):
        raise typer.BadParameter(f"must match {PACKAGE_NAME_PATTERN}", param_hint="NAME")
    root = directory / name
    if root.exists():
        typer.echo(f"{root} already exists", err=True)
        raise typer.Exit(1)
    values = {
        "name": name,
        "kind": kind,
        "author": author,
        "title": name.replace("-", " ").title(),
        "ident": name.replace("-", "_"),
        "prefix": name.split("-")[0],
    }
    files = {"dexterhouse.yaml": templates.MANIFEST, "README.md": templates.README}
    if kind == "agent":
        files |= {"agent.yaml": templates.AGENT, "prompts/system.md": templates.SYSTEM_PROMPT}
    elif kind == "tool":
        files["tool.yaml"] = templates.TOOL
    else:
        files["process.yaml"] = templates.PROCESS
    for rel, text in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text.format(**values), encoding="utf-8")
    typer.echo(f"created {root} ({kind}); next: dexterhouse pkg validate {root}")


def _django() -> None:
    """Set up Django on first use (the commands below need the core database)."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dexterhouse.settings.dev")
    import django
    from django.apps import apps

    if not apps.ready:
        django.setup()


def _organization(slug: str | None) -> Any:
    if slug is None:
        return None
    from dexterhouse.apps.accounts.models import Organization

    org = Organization.objects.filter(slug=slug).first()
    if org is None:
        raise typer.BadParameter(f"no organization {slug!r}", param_hint="--org")
    return org


def _package(name: str, org: Any) -> Any:
    from dexterhouse.apps.packages.models import Package

    package = Package.objects.filter(organization=org, name=name, deleted_at__isnull=True).first()
    if package is None:
        scope = f"organization {org.slug}" if org else "the global packages"
        typer.echo(f"{name} is not installed in {scope}", err=True)
        raise typer.Exit(1)
    return package


@app.command()
def install(
    source: Annotated[
        str, typer.Argument(help="Folder (development), git+https://…@tag, or a registry name.")
    ],
    version: Annotated[
        str, typer.Option("--version", "-v", help="Registry version (names only).")
    ] = "",
    org: Annotated[
        str | None, typer.Option("--org", help="Organization slug (default: global).")
    ] = None,
    confirm_permissions: Annotated[
        bool,
        typer.Option(
            "--confirm-permissions",
            help="Accept the listed risk: high permissions without asking.",
        ),
    ] = False,
) -> None:
    """Install or upgrade a package; `risk: high` permissions need explicit consent."""
    _django()
    from dexterhouse.apps.packages.services import installer
    from dexterhouse.common.errors import DomainError

    if Path(source).expanduser().is_dir():
        source = str(Path(source).expanduser().resolve())
    try:
        done = installer.install(organization=_organization(org), source=source, version=version)
    except DomainError as exc:
        typer.echo(f"error: {exc.detail}", err=True)
        raise typer.Exit(2) from exc
    for warning in done.warnings:
        typer.secho(f"warning: {warning}", err=True, fg="yellow")
    if done.status == "awaiting_consent":
        done = _consent(done, confirm_permissions)
    if done.status != "installed":
        for error in done.errors:
            typer.secho(f"error: {error}", err=True, fg="red")
        typer.echo(f"{done.name or source}: {done.status} ({done.reason})", err=True)
        raise typer.Exit(EXIT_CONSENT if done.reason == "declined" else 1)
    typer.echo(f"installed {done.name}@{done.version} ({done.kind}, {done.source})")


def _consent(done: Any, confirmed: bool) -> Any:
    from dexterhouse.apps.packages.services import installer

    typer.echo(f"{done.name}@{done.version} requires these high-risk permissions:")
    for permission in done.consent_required:
        typer.echo(f"  - {permission['id']} (high): {permission.get('description') or ''}")
    if not confirmed:
        if not sys.stdin.isatty():
            typer.echo("re-run with --confirm-permissions to accept them", err=True)
        confirmed = sys.stdin.isatty() and typer.confirm("Grant them?", default=False)
    return installer.consent(done.id, user=None, accept=confirmed)


@app.command("list")
def list_(
    org: Annotated[
        str | None, typer.Option("--org", help="Organization slug (default: global).")
    ] = None,
    kind: Annotated[str | None, typer.Option("--kind", "-k", help="agent | tool | process")] = None,
) -> None:
    """List the installed packages (global ones, plus the organization's with --org)."""
    _django()
    from dexterhouse.apps.packages.services.catalog import visible_packages

    organization = _organization(org)
    rows = visible_packages(organization.id if organization else None)
    if kind:
        rows = rows.filter(kind=kind)
    for package in rows.select_related("enabled_version").order_by("kind", "name"):
        version = package.enabled_version.version if package.enabled_version else "-"
        scope = "global" if package.organization_id is None else org
        typer.echo(
            f"{package.name:<32} {version:<10} {package.kind:<8} {package.source:<12} "
            f"{package.status:<17} {scope}"
        )


def _lifecycle(action: str, name: str, org: str | None) -> None:
    _django()
    from dexterhouse.apps.packages.services import lifecycle
    from dexterhouse.common.errors import DomainError

    package = _package(name, _organization(org))
    try:
        getattr(lifecycle, action)(package)
    except DomainError as exc:
        typer.echo(f"error: {exc.detail}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"{name}: {action}d")


@app.command()
def remove(
    name: str,
    org: Annotated[
        str | None, typer.Option("--org", help="Organization slug (default: global).")
    ] = None,
) -> None:
    """Remove a package and its files (refused while active projects use it)."""
    _lifecycle("remove", name, org)


@app.command()
def disable(
    name: str,
    org: Annotated[
        str | None, typer.Option("--org", help="Organization slug (default: global).")
    ] = None,
) -> None:
    """Hide a package from new hires and projects (active projects keep their version)."""
    _lifecycle("disable", name, org)


@app.command()
def enable(
    name: str,
    org: Annotated[
        str | None, typer.Option("--org", help="Organization slug (default: global).")
    ] = None,
) -> None:
    """Enable a disabled package again (if compat.core and its role still fit)."""
    _lifecycle("enable", name, org)
