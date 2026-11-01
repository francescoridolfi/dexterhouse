# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from schema_helpers import PACKAGES, assert_invalid, patched

from dexterhouse_schema import SkillFrontmatter
from dexterhouse_schema.skill import split_skill_md

SKILL_MD = (PACKAGES / "security-reviewer/skills/owasp-top10/SKILL.md").read_text()
FRONTMATTER = split_skill_md(SKILL_MD).frontmatter


def test_doc_example_is_valid() -> None:
    doc = split_skill_md(SKILL_MD)
    meta = SkillFrontmatter.model_validate(doc.frontmatter)
    assert meta.name == "owasp-top10"
    assert meta.dexterhouse is not None
    assert meta.dexterhouse.tools_required == ["workspace.read", "git.diff"]
    assert doc.body.lstrip().startswith("# OWASP Top 10 review")


def test_unknown_top_level_keys_are_tolerated() -> None:
    meta = SkillFrontmatter.model_validate(patched(FRONTMATTER, {"allowed-tools": ["Read"]}))
    assert meta.model_extra == {"allowed-tools": ["Read"]}


def test_skill_without_dexterhouse_block() -> None:
    meta = SkillFrontmatter.model_validate({"name": "plain-skill", "description": "Generic."})
    assert meta.dexterhouse is None


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"dexterhouse.priority": 1}, "Extra inputs"),
        ({"dexterhouse.schema": 2}, "unsupported schema"),
        ({"dexterhouse.cost_hint": "huge"}, "cost_hint"),
        ({"dexterhouse.tools_required": ["read"]}, "pattern"),
        ({"description": "x" * 1025}, "at most 1024"),
        ({"description": ""}, "at least 1"),
        ({"name": "OWASP"}, "pattern"),
    ],
)
def test_invalid(changes: dict[str, object], match: str) -> None:
    assert_invalid(SkillFrontmatter, patched(FRONTMATTER, changes), match)


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("# no frontmatter\n", "must start with"),
        ("", "must start with"),
        ("---\nname: x\n", "unterminated"),
        ("---\n- a\n- b\n---\nbody", "mapping"),
        ("---\nname: [unclosed\n---\nbody", "invalid YAML"),
    ],
)
def test_split_errors(text: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        split_skill_md(text)
