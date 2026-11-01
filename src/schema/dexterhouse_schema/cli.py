# SPDX-License-Identifier: AGPL-3.0-or-later
"""`dexterhouse-schema` command line.

`validate <path>` and `export-jsonschema <out_dir>`, plus the registry CI commands of
:mod:`dexterhouse_schema.registry_cli` (`hash`, `scan-prompts`, `check-entry`,
`check-registry-update`).
"""

import argparse
import sys
from collections.abc import Sequence

from dexterhouse_schema import __version__, registry_cli
from dexterhouse_schema.jsonschema import export_json_schemas
from dexterhouse_schema.validate import validate_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dexterhouse-schema", description="Validate DexterHouse packages and files."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate a package directory or a file")
    validate.add_argument("path")
    export = commands.add_parser("export-jsonschema", help="write the JSON Schemas")
    export.add_argument("out_dir")
    registry_cli.add_commands(commands)
    return parser


def _validate(path: str) -> int:
    report = validate_path(path)
    for warning in report.warnings:
        sys.stderr.write(f"warning: {warning}\n")
    for error in report.errors:
        sys.stderr.write(f"error: {error}\n")
    if not report.ok:
        sys.stderr.write(f"{path}: invalid ({len(report.errors)} error(s))\n")
        return 1
    sys.stdout.write(f"{path}: valid\n")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI; returns the exit code (0 ok, 1 invalid or failed, 2 usage error)."""
    args = _build_parser().parse_args(argv)
    if args.command == "validate":
        return _validate(args.path)
    if args.command != "export-jsonschema":
        return registry_cli.run(args)
    for path in export_json_schemas(args.out_dir):
        sys.stdout.write(f"{path}\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
