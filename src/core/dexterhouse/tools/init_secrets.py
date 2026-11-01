# SPDX-License-Identifier: AGPL-3.0-or-later
"""Generate missing secrets into a directory (compose `secrets-init`, idempotent).

Usage: `python -m dexterhouse.tools.init_secrets /run/dh-secrets`. Existing files are never
overwritten, so restarts keep the same keys.
"""

import base64
import os
import secrets
import sys
from collections.abc import Callable
from pathlib import Path

GENERATORS: dict[str, Callable[[], str]] = {
    "secret_key": lambda: secrets.token_urlsafe(50),
    "fernet_key": lambda: base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"),
    "runner_key": lambda: secrets.token_hex(32),
    "pg_password": lambda: secrets.token_hex(24),
}


def init_secrets(directory: Path) -> list[str]:
    """Create each missing secret file and return the names that were created."""
    directory.mkdir(parents=True, exist_ok=True)
    created = []
    for name, generate in GENERATORS.items():
        path = directory / name
        if path.exists():
            continue
        path.write_text(generate(), encoding="utf-8")
        # Readable by the other service users (postgres, dexterhouse) inside the private volume.
        path.chmod(0o644)
        created.append(name)
    return created


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        sys.stderr.write("usage: python -m dexterhouse.tools.init_secrets <directory>\n")
        return 2
    created = init_secrets(Path(args[0]))
    sys.stdout.write(f"created: {', '.join(created) or 'none'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
