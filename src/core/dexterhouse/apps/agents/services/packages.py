# SPDX-License-Identifier: AGPL-3.0-or-later
"""Load agent and tool packages (validated with `dexterhouse-schema`).

Which packages exist comes from the installed PackageVersions (`apps.packages`); the
files are read from each version's `install_path`.
"""

import uuid
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog
from django.conf import settings

from dexterhouse_schema.agent import Agent
from dexterhouse_schema.package import validate_package
from dexterhouse_schema.skill import SkillFrontmatter, split_skill_md
from dexterhouse_schema.tool import Permission, Tool

logger = structlog.get_logger(__name__)


def builtin_tools_dir() -> Path:
    """`settings.BUILTIN_DIR / tools`: `src/builtin` in a checkout, `/app/builtin` in the image."""
    return Path(settings.BUILTIN_DIR) / "tools"


def builtin_skills_dir() -> Path:
    """`settings.BUILTIN_DIR / skills`: skills shared by every agent (skill.md)."""
    return Path(settings.BUILTIN_DIR) / "skills"


class PackageError(ValueError):
    """The package is missing or invalid: a configuration error, never retried."""


@dataclass(frozen=True)
class SkillInfo:
    name: str
    description: str
    tools_required: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentPackage:
    root: Path
    name: str
    version: str
    agent: Agent
    system_prompt: str
    skills: tuple[SkillInfo, ...] = ()
    version_id: uuid.UUID | None = None
    """The installed PackageVersion (None when loaded from a bare folder)."""
    source: str = "local"


@dataclass(frozen=True)
class ToolBinding:
    """A permission id bound to the MCP server (tool package) that implements it."""

    permission: Permission
    tool: Tool
    root: Path
    builtin: bool


@dataclass(frozen=True)
class ToolCatalog:
    bindings: dict[str, ToolBinding] = field(default_factory=dict)

    def get(self, permission_id: str) -> ToolBinding | None:
        return self.bindings.get(permission_id)


def load_agent_package(path: str | Path) -> AgentPackage:
    root = Path(path).resolve()
    return _load_agent(str(root), _mtime(root))


@lru_cache(maxsize=64)
def _load_agent(root_str: str, _mtime: float) -> AgentPackage:
    root = Path(root_str)
    report = validate_package(root)
    if report.errors:
        raise PackageError(f"invalid agent package {root}: {report.errors[0]}")
    agent = report.models.get("agent.yaml")
    manifest = report.models.get("dexterhouse.yaml")
    if not isinstance(agent, Agent) or manifest is None:
        raise PackageError(f"{root} is not an agent package")
    skills = [_skill_info(root / "skills" / name) for name in agent.skills]
    return AgentPackage(
        root=root,
        name=manifest.name,  # type: ignore[attr-defined]
        version=manifest.version,  # type: ignore[attr-defined]
        agent=agent,
        system_prompt=(root / agent.prompts.system).read_text(encoding="utf-8"),
        skills=tuple(skills),
    )


def _skill_info(folder: Path) -> SkillInfo:
    doc = split_skill_md((folder / "SKILL.md").read_text(encoding="utf-8"))
    front = SkillFrontmatter.model_validate(doc.frontmatter)
    required = tuple(front.dexterhouse.tools_required) if front.dexterhouse else ()
    return SkillInfo(front.name, front.description, required)


def shared_skills() -> tuple[SkillInfo, ...]:
    """The built-in skills every agent may load (`BUILTIN_DIR/skills/<name>/SKILL.md`).

    The context builder lists those whose `tools_required` the agent has; an invalid
    skill folder is skipped (the registry CI and the package tests validate them).
    """
    base = builtin_skills_dir()
    folders = sorted(p.parent for p in base.glob("*/SKILL.md")) if base.is_dir() else []
    stamp = max((p.stat().st_mtime for p in base.glob("*/SKILL.md")), default=0.0)
    return _shared_skills(tuple(str(f) for f in folders), stamp)


@lru_cache(maxsize=8)
def _shared_skills(folders: tuple[str, ...], _mtime: float) -> tuple[SkillInfo, ...]:
    skills = []
    for folder in folders:
        try:
            skills.append(_skill_info(Path(folder)))
        except ValueError:
            continue
    return tuple(skills)


def installed_agent_packages(organization_id: uuid.UUID | None = None) -> list[AgentPackage]:
    """The enabled agent packages an organization sees, built-in first."""
    from dexterhouse.apps.packages.services.catalog import enabled_versions

    return [
        package
        for version in enabled_versions("agent", organization_id)
        if (package := agent_package_for(version)) is not None
    ]


def agent_package_for(version: Any) -> AgentPackage | None:
    """Load an installed PackageVersion; None (logged) if its files are missing or invalid."""
    try:
        package = load_agent_package(version.install_path)
    except PackageError as exc:
        logger.warning("agents.package_invalid", path=version.install_path, error=str(exc))
        return None
    return replace(package, version_id=version.id, source=version.package.source)


def load_tool_catalog(
    dirs: list[Path] | None = None, *, organization_id: uuid.UUID | None = None
) -> ToolCatalog:
    """Every permission of every enabled tool package; the first package wins on duplicates.

    `dirs` scans package folders instead (tests and tooling that work on bare folders).
    """
    if dirs is not None:
        roots = [
            (root, False)
            for base in dirs
            if base.is_dir()
            for root in sorted(p.parent for p in base.glob("*/tool.yaml"))
        ]
    else:
        from dexterhouse.apps.packages.services.catalog import enabled_versions

        roots = [
            (Path(v.install_path), v.package.source == "builtin")
            for v in enabled_versions("tool", organization_id)
        ]
    bindings: dict[str, ToolBinding] = {}
    for root, builtin in roots:
        try:
            tool = _load_tool(str(root.resolve()), _mtime(root))
        except PackageError:
            logger.warning("agents.tool_package_missing", path=str(root))
            continue
        if tool is None:
            continue
        for permission in tool.permissions:
            bindings.setdefault(
                permission.id, ToolBinding(permission, tool, root.resolve(), builtin=builtin)
            )
    return ToolCatalog(bindings)


@lru_cache(maxsize=128)
def _load_tool(root_str: str, _mtime: float) -> Tool | None:
    report = validate_package(root_str)
    tool = report.models.get("tool.yaml")
    return tool if not report.errors and isinstance(tool, Tool) else None


def _mtime(root: Path) -> float:
    try:
        return max(p.stat().st_mtime for p in root.glob("*.yaml"))
    except ValueError as exc:
        raise PackageError(f"no package at {root}") from exc
