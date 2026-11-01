# SPDX-License-Identifier: AGPL-3.0-or-later
"""Validation of one `skills/<name>/` folder."""

import re
from pathlib import Path

from pydantic import ValidationError

from dexterhouse_schema.common import check_relative_path
from dexterhouse_schema.loader import read_text
from dexterhouse_schema.prompts import scan_text
from dexterhouse_schema.report import ValidationReport
from dexterhouse_schema.skill import MAX_SKILL_BODY_CHARS, SkillFrontmatter, split_skill_md

_LINK_RE = re.compile(r"\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
_EXTERNAL_RE = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|#)")


def report_patterns(text: str, rel: str, report: ValidationReport) -> None:
    """Record every forbidden prompt pattern found in `text`."""
    for match in scan_text(text):
        report.error(
            rel, f"forbidden pattern {match.pattern_id}: {match.excerpt!r}", f"line {match.line}"
        )


def validate_skill_dir(skill_dir: Path, rel_dir: str, report: ValidationReport) -> None:
    """Frontmatter, `name` = folder name, body length, forbidden patterns, local links."""
    rel = f"{rel_dir}/SKILL.md"
    path = skill_dir / "SKILL.md"
    if not path.is_file():
        report.error(rel, "missing SKILL.md")
        return
    text = read_text(path, rel, report)
    if text is None:
        return
    try:
        doc = split_skill_md(text)
        meta = SkillFrontmatter.model_validate(doc.frontmatter)
    except ValueError as exc:
        if isinstance(exc, ValidationError):
            report.add_validation_error(rel, exc)
        else:
            report.error(rel, str(exc))
        return
    report.models[rel] = meta
    if meta.name != skill_dir.name:
        report.error(rel, f"name {meta.name!r} must equal the folder name {skill_dir.name!r}")
    if len(doc.body) > MAX_SKILL_BODY_CHARS:
        report.error(rel, f"body has {len(doc.body)} characters, limit {MAX_SKILL_BODY_CHARS}")
    report_patterns(text, rel, report)
    _check_links(doc.body, skill_dir, rel, report)


def _check_links(body: str, skill_dir: Path, rel: str, report: ValidationReport) -> None:
    for target in _LINK_RE.findall(body):
        if _EXTERNAL_RE.match(target):
            continue
        local = target.split("#", 1)[0]
        try:
            check_relative_path(local)
        except ValueError as exc:
            report.error(rel, f"support file link: {exc}")
            continue
        resolved = (skill_dir / local).resolve()
        if not resolved.is_relative_to(skill_dir.resolve()) or not resolved.is_file():
            report.error(rel, f"support file {local!r} does not exist in the skill folder")
