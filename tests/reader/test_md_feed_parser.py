from time import struct_time

from reader.md_feed_parser import is_markdown_feed, parse_md_feed

URL = "https://example.com/release-notes.md.txt"

SAMPLE_MD = """\
Some introductory text before any headings.

## May 28, 2026

Feature

### New Feature Title

Body text here with details.

## May 27, 2026

Feature **Inline Title Without H3**

Description of the feature.

## Introduction

This is not a date heading and should be skipped.

## May 26, 2026

"""


class TestParseMdFeed:
    def test_parses_date_sections(self):
        entries = parse_md_feed(URL, SAMPLE_MD)
        assert len(entries) == 2
        assert entries[0]["title"] == "May 28, 2026"
        assert entries[1]["title"] == "May 27, 2026"

    def test_content_included(self):
        entries = parse_md_feed(URL, SAMPLE_MD)
        assert "New Feature Title" in entries[0]["summary"]
        assert "Inline Title Without H3" in entries[1]["summary"]

    def test_published_parsed_fields(self):
        entries = parse_md_feed(URL, SAMPLE_MD)
        t = entries[0]["published_parsed"]
        assert isinstance(t, struct_time)
        assert t.tm_year == 2026
        assert t.tm_mon == 5
        assert t.tm_mday == 28

    def test_second_entry_published(self):
        entries = parse_md_feed(URL, SAMPLE_MD)
        t = entries[1]["published_parsed"]
        assert t.tm_year == 2026
        assert t.tm_mon == 5
        assert t.tm_mday == 27

    def test_unique_ids(self):
        entries = parse_md_feed(URL, SAMPLE_MD)
        ids = [e["id"] for e in entries]
        assert len(ids) == len(set(ids))

    def test_id_contains_url(self):
        entries = parse_md_feed(URL, SAMPLE_MD)
        assert all(e["id"].startswith(URL) for e in entries)

    def test_link_is_url(self):
        entries = parse_md_feed(URL, SAMPLE_MD)
        assert all(e["link"] == URL for e in entries)

    def test_skips_non_date_h2(self):
        entries = parse_md_feed(URL, SAMPLE_MD)
        titles = [e["title"] for e in entries]
        assert "Introduction" not in titles

    def test_skips_empty_sections(self):
        # May 26 セクションは内容なしなのでスキップされる
        entries = parse_md_feed(URL, SAMPLE_MD)
        titles = [e["title"] for e in entries]
        assert "May 26, 2026" not in titles

    def test_empty_text(self):
        entries = parse_md_feed(URL, "")
        assert entries == []

    def test_no_date_sections(self):
        text = "# Title\n\nSome text without date sections."
        entries = parse_md_feed(URL, text)
        assert entries == []

    def test_single_section(self):
        text = "## January 1, 2025\n\nContent here."
        entries = parse_md_feed(URL, text)
        assert len(entries) == 1
        assert entries[0]["title"] == "January 1, 2025"
        assert entries[0]["published_parsed"].tm_year == 2025
        assert entries[0]["published_parsed"].tm_mon == 1
        assert entries[0]["published_parsed"].tm_mday == 1


class TestIsMarkdownFeed:
    def test_md_extension(self):
        assert is_markdown_feed({"url": "https://example.com/notes.md"}) is True

    def test_md_txt_extension(self):
        assert is_markdown_feed({"url": "https://example.com/notes.md.txt"}) is True

    def test_type_markdown(self):
        assert is_markdown_feed({"url": "https://example.com/updates", "type": "markdown"}) is True

    def test_rss_url(self):
        assert is_markdown_feed({"url": "https://example.com/feed.xml"}) is False

    def test_atom_url(self):
        assert is_markdown_feed({"url": "https://example.com/atom"}) is False

    def test_no_url(self):
        assert is_markdown_feed({}) is False
