from research.main import build_output_content, link_citations, parse_sources


SAMPLE_BODY = (
    "本文中に [cite: 1, 2] という引用があり、別段落にも [cite: 3] があります。\n"
    "\n"
    "**Sources:**\n"
    "1. [example.com](https://example.com/1)\n"
    "2. [foo.org](https://foo.org/2)\n"
    "3. [bar.net](https://bar.net/3)\n"
)


class TestParseSources:
    def test_parses_numbered_sources(self):
        sources = parse_sources(SAMPLE_BODY)
        assert sources == {
            1: "https://example.com/1",
            2: "https://foo.org/2",
            3: "https://bar.net/3",
        }

    def test_returns_empty_when_no_sources_section(self):
        assert parse_sources("本文だけ [cite: 1]") == {}


class TestLinkCitations:
    def test_replaces_multi_number_cite(self):
        result = link_citations(SAMPLE_BODY)
        assert (
            "<sup>[1](https://example.com/1),[2](https://foo.org/2)</sup>"
            in result
        )
        assert "[cite: 1, 2]" not in result

    def test_replaces_single_number_cite(self):
        result = link_citations(SAMPLE_BODY)
        assert "<sup>[3](https://bar.net/3)</sup>" in result
        assert "[cite: 3]" not in result

    def test_no_sources_keeps_cite_as_is(self):
        text = "引用 [cite: 1] が残る"
        assert link_citations(text) == text

    def test_missing_source_number_renders_plain(self):
        text = (
            "引用 [cite: 99] は対応なし\n\n"
            "**Sources:**\n1. [a](https://a.example)"
        )
        result = link_citations(text)
        assert "<sup>[99]</sup>" in result


class TestBuildOutputContent:
    def test_renders_query_and_links(self):
        content = build_output_content("クエリ", SAMPLE_BODY)
        assert content.startswith("# Query\n\nクエリ\n\n---\n\n")
        assert "<sup>[1](https://example.com/1)," in content
        assert "[cite:" not in content