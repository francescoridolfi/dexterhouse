# SPDX-License-Identifier: AGPL-3.0-or-later
"""Registry CI subcommands: `hash`, `scan-prompts`, `check-entry`, `check-registry-update`."""

import argparse
import sys
from pathlib import Path

from dexterhouse_schema.loader import load_model
from dexterhouse_schema.registry import RegistryPackage, check_registry_update
from dexterhouse_schema.registry_check import HashError, archive_sha256, check_entry, scan_prompts
from dexterhouse_schema.report import ValidationReport
from dexterhouse_schema.validate import validate_registry_package_file


def add_commands(commands: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    hash_cmd = commands.add_parser("hash", help="sha256 of `git archive --format=tar <ref>`")
    hash_cmd.add_argument("path", help="git repository (the package checkout)")
    hash_cmd.add_argument("--ref", default="HEAD", help="tag or commit (default HEAD)")
    scan = commands.add_parser("scan-prompts", help="forbidden patterns in prompts and skills")
    scan.add_argument("path")
    entry = commands.add_parser("check-entry", help="registry entry vs the package checkout")
    entry.add_argument("entry", help="packages/<name>.json")
    entry.add_argument("path", help="package directory")
    entry.add_argument("--version", default=None, help="version to check (default latest)")
    update = commands.add_parser(
        "check-registry-update", help="rules on a change to packages/<name>.json"
    )
    update.add_argument("old", help="version on main; an empty file for a new package")
    update.add_argument("new")
    update.add_argument("--maintainer", action="store_true", help="the PR author is a maintainer")


def run(args: argparse.Namespace) -> int:
    handlers = {
        "hash": _hash,
        "scan-prompts": _scan,
        "check-entry": _check_entry,
        "check-registry-update": _check_update,
    }
    return handlers[args.command](args)


def _fail(path: str, errors: list[str]) -> int:
    for error in errors:
        sys.stderr.write(f"error: {error}\n")
    sys.stderr.write(f"{path}: {len(errors)} error(s)\n")
    return 1


def _load_entry(path: str) -> tuple[RegistryPackage | None, ValidationReport]:
    report = validate_registry_package_file(Path(path))
    model = report.models.get(Path(path).name)
    return (model if isinstance(model, RegistryPackage) else None), report


def _hash(args: argparse.Namespace) -> int:
    try:
        sys.stdout.write(f"{archive_sha256(args.path, args.ref)}\n")
    except HashError as exc:
        return _fail(args.path, [str(exc)])
    return 0


def _scan(args: argparse.Namespace) -> int:
    if not Path(args.path).is_dir():
        return _fail(args.path, ["not a directory"])
    hits = scan_prompts(args.path)
    if hits:
        return _fail(args.path, hits)
    sys.stdout.write(f"{args.path}: no forbidden patterns\n")
    return 0


def _check_entry(args: argparse.Namespace) -> int:
    entry, report = _load_entry(args.entry)
    if entry is None or not report.ok:
        return _fail(args.entry, [str(issue) for issue in report.errors])
    errors = check_entry(entry, args.path, args.version)
    if errors:
        return _fail(args.path, errors)
    sys.stdout.write(f"{args.path}: matches {args.entry}\n")
    return 0


def _check_update(args: argparse.Namespace) -> int:
    old: RegistryPackage | None = None
    if not Path(args.old).is_file():
        return _fail(args.old, ["no such file (use an empty file for a new package)"])
    if Path(args.old).read_text(encoding="utf-8").strip():
        report = ValidationReport()
        old = load_model(Path(args.old), args.old, RegistryPackage, report)
        if old is None:
            return _fail(args.old, [str(issue) for issue in report.errors])
    new, report = _load_entry(args.new)
    if new is None or not report.ok:
        return _fail(args.new, [str(issue) for issue in report.errors])
    errors = check_registry_update(old, new, by_maintainer=args.maintainer)
    if errors:
        return _fail(args.new, errors)
    sys.stdout.write(f"{args.new}: {'new package' if old is None else 'valid update'}\n")
    return 0
