# SPDX-License-Identifier: AGPL-3.0-or-later
"""Validation of a whole package directory (what `pkg validate` and the registry CI run)."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from dexterhouse_schema.agent import Agent
from dexterhouse_schema.loader import UNREADABLE, load_data, load_model, read_text
from dexterhouse_schema.manifest import DEFINITION_FILES, Manifest
from dexterhouse_schema.process import Process
from dexterhouse_schema.prompts import MAX_SYSTEM_PROMPT_CHARS
from dexterhouse_schema.report import ValidationReport
from dexterhouse_schema.skill_check import report_patterns, validate_skill_dir
from dexterhouse_schema.tool import LAUNCHERS, Tool
from dexterhouse_schema.tree import check_tree, resolve_ref

MANIFEST_FILE = "dexterhouse.yaml"
MAX_ICON_BYTES = 256 * 1024
MAX_AVATAR_BYTES = 2 * 1024 * 1024
DEFINITION_MODELS: dict[str, type[BaseModel]] = {
    "agent": Agent,
    "tool": Tool,
    "process": Process,
}


def validate_package(path: str | Path) -> ValidationReport:
    """Validate the package rooted at `path`; never raises for invalid content.

    Checks the manifest, the definition file matching its `kind`, referenced files,
    prompts, skills and the file tree. Process inputs the project brief must provide
    are reported as warnings.
    """
    root = Path(path)
    report = ValidationReport()
    if not root.is_dir():
        report.error(str(root), "not a directory")
        return report
    _PackageChecker(root, report).run()
    return report


class _PackageChecker:
    def __init__(self, root: Path, report: ValidationReport) -> None:
        self.root = root
        self.report = report
        self.exempt: set[str] = set()

    def run(self) -> None:
        manifest = load_model(self.root / MANIFEST_FILE, MANIFEST_FILE, Manifest, self.report)
        kind = manifest.kind if manifest else self._raw_kind()
        definition = self._load_definition(kind) if kind else None
        if manifest:
            self._ref(MANIFEST_FILE, manifest.readme, "readme")
            if manifest.icon:
                self._ref(MANIFEST_FILE, manifest.icon, "icon", MAX_ICON_BYTES)
        if isinstance(definition, Agent):
            self._check_agent(definition)
        elif isinstance(definition, Tool):
            self._check_tool(definition, manifest)
        elif isinstance(definition, Process):
            self._check_process(definition, manifest)
        self._check_skills(definition.skills if isinstance(definition, Agent) else [])
        check_tree(self.root, self.report, frozenset(self.exempt))

    def _raw_kind(self) -> str | None:
        path = self.root / MANIFEST_FILE
        if not path.is_file():
            return None
        data: Any = load_data(path, MANIFEST_FILE, ValidationReport())
        kind = data.get("kind") if data is not UNREADABLE and isinstance(data, dict) else None
        return kind if kind in DEFINITION_FILES else None

    def _load_definition(self, kind: str) -> BaseModel | None:
        expected = DEFINITION_FILES[kind]
        for other in DEFINITION_FILES.values():
            if other != expected and (self.root / other).exists():
                self.report.error(other, f"unexpected definition file: manifest kind is {kind}")
        if not (self.root / expected).is_file():
            self.report.error(expected, f"missing definition file for kind {kind}")
            return None
        return load_model(self.root / expected, expected, DEFINITION_MODELS[kind], self.report)

    def _ref(self, source: str, value: str, loc: str, max_bytes: int | None = None) -> Path | None:
        return resolve_ref(self.root, value, self.report, source, loc, max_bytes)

    def _check_agent(self, agent: Agent) -> None:
        system = self._ref("agent.yaml", agent.prompts.system, "prompts.system")
        if system and (text := read_text(system, agent.prompts.system, self.report)) is not None:
            if len(text) > MAX_SYSTEM_PROMPT_CHARS:
                self.report.error(
                    agent.prompts.system,
                    f"system prompt has {len(text)} characters, limit {MAX_SYSTEM_PROMPT_CHARS}",
                )
            report_patterns(text, agent.prompts.system, self.report)
        if agent.prompts.examples:
            examples = self._ref("agent.yaml", agent.prompts.examples, "prompts.examples")
            if examples and (text := read_text(examples, agent.prompts.examples, self.report)):
                report_patterns(text, agent.prompts.examples, self.report)
        if agent.office.avatar:
            if Path(agent.office.avatar).suffix.lower() not in {".glb", ".gltf"}:
                self.report.error(
                    "agent.yaml", "avatar must be a .glb or .gltf file", "office.avatar"
                )
            self._ref("agent.yaml", agent.office.avatar, "office.avatar", MAX_AVATAR_BYTES)

    def _check_tool(self, tool: Tool, manifest: Manifest | None) -> None:
        if manifest and tool.name != manifest.name:
            self.report.error("tool.yaml", f"must equal manifest name {manifest.name!r}", "name")
        launcher = tool.command[0] if tool.command else None
        if launcher and launcher not in LAUNCHERS:
            if self._ref("tool.yaml", launcher, "command[0]"):
                self.exempt.add(Path(launcher).as_posix())

    def _check_process(self, process: Process, manifest: Manifest | None) -> None:
        if manifest:
            for field in ("name", "version"):
                if getattr(process, field) != getattr(manifest, field):
                    self.report.error(
                        "process.yaml",
                        f"must equal manifest {field} {getattr(manifest, field)!r}",
                        field,
                    )
        for kind, phases in process.brief_requirements().items():
            self.report.warn(
                "process.yaml",
                f"process requires `{kind}` in the project brief "
                f"(phase(s) {', '.join(phases)} use a workspace and no upstream phase produces it)",
            )

    def _check_skills(self, declared: list[str]) -> None:
        skills_dir = self.root / "skills"
        on_disk = (
            sorted(p.name for p in skills_dir.iterdir() if p.is_dir())
            if skills_dir.is_dir()
            else []
        )
        for index, name in enumerate(declared):
            if name not in on_disk:
                self.report.error(
                    "agent.yaml", f"skill folder skills/{name} not found", f"skills[{index}]"
                )
        for name in on_disk:
            validate_skill_dir(skills_dir / name, f"skills/{name}", self.report)
            if name not in declared:
                self.report.warn(f"skills/{name}", "skill folder not listed in agent.yaml skills")
