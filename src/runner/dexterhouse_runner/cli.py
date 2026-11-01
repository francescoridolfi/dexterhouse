# SPDX-License-Identifier: AGPL-3.0-or-later
"""Command line entry point of the runner (skeleton until the runner epic)."""

import sys

from dexterhouse_runner import __version__


def main(argv: list[str] | None = None) -> int:
    """Run a runner subcommand; only `health` and `version` exist in Sprint 0."""
    args = sys.argv[1:] if argv is None else argv
    command = args[0] if args else "health"
    if command == "version":
        sys.stdout.write(f"{__version__}\n")
        return 0
    if command == "health":
        sys.stdout.write("ok\n")
        return 0
    sys.stderr.write(f"unknown command: {command}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
