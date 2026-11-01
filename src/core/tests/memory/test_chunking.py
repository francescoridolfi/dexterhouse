# SPDX-License-Identifier: AGPL-3.0-or-later
from dexterhouse.apps.memory.services.chunking import chunk_markdown, chunk_structured

from .conftest import ARCHITECTURE


def test_markdown_by_heading():
    chunks = chunk_markdown(ARCHITECTURE)
    assert [c.heading for c in chunks] == ["Architecture", "Data model", "Modules"]
    assert chunks[1].content.startswith("## Data model")
    assert "FIFO" in chunks[1].content


def test_code_fences_are_not_headings_and_preamble_is_kept():
    text = "Preamble.\n\n## Setup\n\n```bash\n# not a heading\nmake\n```\n"
    chunks = chunk_markdown(text)
    assert [c.heading for c in chunks] == ["", "Setup"]
    assert "# not a heading" in chunks[1].content


def test_long_sections_split_at_paragraphs():
    paragraphs = "\n\n".join(f"Paragraph {i} " + "x" * 300 for i in range(10))
    chunks = chunk_markdown(f"## Long\n\n{paragraphs}\n\n" + "y" * 5000, max_chars=1000)
    assert all(len(c.content) <= 1000 for c in chunks)
    assert {c.heading for c in chunks} == {"Long"}
    assert sum(c.content.count("Paragraph") for c in chunks) == 10
    assert chunk_markdown("") == []


def test_structured_items_are_merged_up_to_the_limit():
    data = {
        "language": "python",
        "tasks": [{"id": f"T-{i:02d}", "title": "t" * 50} for i in range(30)],
    }
    chunks = chunk_structured(data, max_chars=500)
    assert chunks[0].content.startswith('language: "python"')
    assert all(len(c.content) <= 500 for c in chunks)
    assert sum(c.content.count('"id"') for c in chunks) == 30
    assert chunk_structured([1, 2])[0].content.startswith("items[0]")
