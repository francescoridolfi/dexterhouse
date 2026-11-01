# SPDX-License-Identifier: AGPL-3.0-or-later
"""`python -m dexterhouse_runner.workspace_mcp` (the image's `dexterhouse-workspace-mcp`)."""

import sys

from dexterhouse_runner.workspace_mcp.server import main

if __name__ == "__main__":
    sys.exit(main())
