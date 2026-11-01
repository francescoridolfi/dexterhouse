# SPDX-License-Identifier: AGPL-3.0-or-later
"""Load agent and tool packages from disk (validated with `dexterhouse-schema`)."""

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from django.conf import settings

from dexterhouse_schema.agent import Agent
from dexterhouse_schema.package import validate_package
from dexterhouse_schema.skill import SkillFrontmatter, split_skill_md
from dexterhouse_schema.tool import Permission, Tool


def builtin_tools_dir() -> Path:
    """`settings.BUILTIN_DIR / tools`: `src/builtin` in a checkout, `/app/builtin` in the image."""
    return Path(settings.BUILTIN_DIR) / "tools"


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
    skills = []
    for name in agent.skills:
        doc = split_skill_md((root / "skills" / name / "SKILL.md").read_text(encoding="utf-8"))
        front = SkillFrontmatter.model_validate(doc.frontmatter)
        required = tuple(front.dexterhouse.tools_required) if front.dexterhouse else ()
        skills.append(SkillInfo(front.name, front.description, required))
    return AgentPackage(
        root=root,
        name=manifest.name,  # type: ignore[attr-defined]
        version=manifest.version,  # type: ignore[attr-defined]
        agent=agent,
        system_prompt=(root / agent.prompts.system).read_text(encoding="utf-8"),
        skills=tuple(skills),
    )


def tool_package_dirs() -> list[Path]:
    """Built-in tools first, then installed packages (`AGENTS_TOOL_PACKAGE_DIRS`)."""
    extra = [Path(p) for p in getattr(settings, "AGENTS_TOOL_PACKAGE_DIRS", [])]
    return [builtin_tools_dir(), *extra]


def load_tool_catalog(dirs: list[Path] | None = None) -> ToolCatalog:
    """Every permission of every valid tool package; the first package wins on duplicates."""
    bindings: dict[str, ToolBinding] = {}
    builtin = builtin_tools_dir().resolve()
    for base in dirs or tool_package_dirs():
        if not base.is_dir():
            continue
        for root in sorted(p.parent for p in base.glob("*/tool.yaml")):
            tool = _load_tool(str(root.resolve()), _mtime(root))
            if tool is None:
                continue
            for permission in tool.permissions:
                bindings.setdefault(
                    permission.id,
                    ToolBinding(
                        permission, tool, root.resolve(), builtin=base.resolve() == builtin
                    ),
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
