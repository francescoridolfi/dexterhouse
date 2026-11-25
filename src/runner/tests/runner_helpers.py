# SPDX-License-Identifier: AGPL-3.0-or-later
"""Helpers shared by `conftest.py` and the runner tests.

A unique module name: `from conftest import ...` resolves to the core's conftest when
pytest collects both test trees in one run.
"""

import subprocess
from pathlib import Path


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout


STACK = {
    "language": "python",
    "framework": "none",
    "workspace_image": "dexterhouse/workspace:python",
    "package_manager": "uv",
    "test_command": "python3 -c 'print(\"2 passed\")'",
    "run_command": "python3 -m http.server 8000",
    "services": [],
    "env": {"APP_ENV": "test"},
}
