# SPDX-License-Identifier: AGPL-3.0-or-later
"""A small Python + TypeScript project for the code graph tests (kept in code, not files,
so pytest never collects its `tests/`). `src/schema/tests/fixtures/artifacts/code_graph.json`
is its graph: regenerate it with `uv run python src/runner/tests/graph_fixture.py`."""

import json
import subprocess
import sys
from pathlib import Path

FILES = {
    "app/__init__.py": "",
    "app/models.py": (
        "class Base:\n"
        "    def validate(self):\n"
        "        return True\n\n\n"
        "class Course(Base):\n"
        "    def save(self):\n"
        "        self.validate()\n"
        "        return self\n"
    ),
    "app/services.py": (
        "import os\n"
        "import requests\n\n"
        "from app.models import Course\n\n\n"
        "def enroll(name):\n"
        "    course = Course()\n"
        "    course.save()\n"
        "    return helper()\n\n\n"
        "def helper():\n"
        "    return len(os.sep)\n"
    ),
    "app/cli.py": (
        'from . import services\n\nif __name__ == "__main__":\n    services.enroll("x")\n'
    ),
    "tests/test_services.py": (
        'from app.services import enroll\n\n\ndef test_enroll():\n    assert enroll("a") == 1\n'
    ),
    "web/src/api.ts": (
        'import axios from "axios";\n\n'
        "export interface Course {\n  id: number;\n}\n\n"
        "export async function fetchCourses(): Promise<Course[]> {\n"
        '  return (await axios.get("/courses")).data;\n'
        "}\n\n"
        "export const toLabel = (c: Course): string => `#${c.id}`;\n"
    ),
    "web/src/App.tsx": (
        'import React from "react";\n'
        'import { fetchCourses, toLabel as label } from "./api";\n\n'
        "export class App extends React.Component {\n"
        "  load() {\n    return fetchCourses().then((cs) => cs.map(label));\n  }\n"
        "}\n"
    ),
    "web/src/App.test.tsx": 'import { App } from "./App";\n\nnew App({});\n',
    "web/src/main.ts": 'import { App } from "./App";\n\nexport const app = new App({});\n',
    # never analysed
    "web/node_modules/axios/index.js": "export default {};\n",
    ".venv/lib/site.py": "import app\n",
    "build/generated.py": "import app\n",
    "README.md": "# demo\n",
}
FIXED = {"commit": "0" * 40, "generated_at": "2026-11-14T12:00:00Z"}


def write_project(root: Path) -> Path:
    for path, content in FILES.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, "utf-8")
    return root


def fixture_graph(root: Path) -> dict:
    from dexterhouse_runner.workspace_mcp.graph import build_graph

    return {**build_graph(write_project(root)).graph, **FIXED}


if __name__ == "__main__":  # pragma: no cover - regenerates the shared JSON fixture
    import tempfile

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "init", "-q", tmp], check=True)
        graph = fixture_graph(Path(tmp))
    out = Path(__file__).resolve().parents[2] / "schema/tests/fixtures/artifacts/code_graph.json"
    out.write_text(json.dumps(graph, indent=2) + "\n", "utf-8")
    sys.stdout.write(f"wrote {out}\n")
