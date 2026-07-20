from research.main import build_output_content, link_citations


def test_link_citations_uses_urls_from_sources():
    text = """本文です [cite: 1, 2]。

**Sources:**
1. [Example](https://example.com/one)
2. [Other](https://example.com/two)
"""

    result = link_citations(text)

    assert (
        "本文です [1](https://example.com/one), [2](https://example.com/two)。"
        in result
    )
    assert "1. [Example](https://example.com/one)" in result


def test_link_citations_keeps_unknown_source_as_citation_text():
    text = """本文です [cite: 1, 3]。

## Sources
1. [Example](https://example.com/one)
"""

    assert (
        "本文です [1](https://example.com/one), [cite: 3]。"
        in link_citations(text)
    )


def test_link_citations_does_nothing_without_sources_section():
    text = "本文です [cite: 1]。"

    assert link_citations(text) == text


def test_build_output_content_links_citations():
    text = """結果 [cite: 1]。

Sources:
1. [Example](https://example.com)
"""

    result = build_output_content("質問", text)

    assert result.startswith("# Query\n\n質問\n\n---\n\n")
    assert "結果 [1](https://example.com)。" in result
