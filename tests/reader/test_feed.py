import pytest
import yaml

from reader.feed import (
    feed_id,
    feed_importance,
    load_feeds,
    normalize_importance,
    parse_last_fetched,
    save_feeds,
)

_YAML_BLOCK_TEMPLATE = "```yaml\n{yaml_content}```\n"


def _make_feed_md(tmp_path, name, data):
    feed_md = tmp_path / name
    yaml_content = yaml.dump(data, default_flow_style=False, allow_unicode=True)
    feed_md.write_text(_YAML_BLOCK_TEMPLATE.format(yaml_content=yaml_content), encoding="utf-8")
    return feed_md


class TestFeedId:
    def test_returns_id_key(self):
        assert feed_id({"myblog": None, "url": "https://example.com", "title": "Blog"}) == "myblog"

    def test_returns_none_when_no_id(self):
        assert feed_id({"url": "https://example.com", "title": "Blog"}) is None

    def test_roundtrip_via_yaml(self, tmp_path):
        data = {"feeds": [{"myblog": None, "url": "https://example.com", "title": "Blog"}]}
        feed_md = tmp_path / "feed.md"
        save_feeds(data, feed_md)
        loaded = load_feeds(feed_md)
        assert feed_id(loaded["feeds"][0]) == "myblog"

    def test_null_saved_as_empty_value(self, tmp_path):
        data = {"feeds": [{"myblog": None, "url": "https://example.com"}]}
        feed_md = tmp_path / "feed.md"
        save_feeds(data, feed_md)
        content = feed_md.read_text()
        assert "myblog:\n" in content
        assert "null" not in content


class TestLoadFeeds:
    def test_load(self, tmp_path):
        data = {"feeds": [{"url": "https://example.com/rss", "max_articles": 3}]}
        feed_md = _make_feed_md(tmp_path, "feed.md", data)

        result = load_feeds(feed_md)
        assert result == data

    def test_roundtrip(self, tmp_path):
        feed_md = tmp_path / "feed.md"
        data = {
            "feeds": [
                {"url": "https://example.com/rss", "max_articles": 5, "title": "表示名"},
                {"url": "https://other.com/atom", "last_fetched": "2026-03-30T00:00:00+00:00"},
            ]
        }
        save_feeds(data, feed_md)
        assert load_feeds(feed_md) == data

    def test_crlf_line_endings(self, tmp_path):
        data = {"feeds": [{"url": "https://example.com/rss"}]}
        yaml_content = yaml.dump(data, default_flow_style=False, allow_unicode=True)
        crlf_content = f"```yaml\r\n{yaml_content.replace(chr(10), chr(13) + chr(10))}```\r\n"
        feed_md = tmp_path / "feed.md"
        feed_md.write_bytes(crlf_content.encode("utf-8"))

        result = load_feeds(feed_md)
        assert result == data

    def test_no_trailing_newline_before_fence(self, tmp_path):
        """手編集でYAMLコンテンツの末尾改行が欠けても読み込めることを確認"""
        feed_md = tmp_path / "feed.md"
        feed_md.write_text("```yaml\nfeeds: []```\n", encoding="utf-8")
        result = load_feeds(feed_md)
        assert result == {"feeds": []}

    def test_no_yaml_block_raises(self, tmp_path):
        feed_md = tmp_path / "feed.md"
        feed_md.write_text("# No YAML here\n", encoding="utf-8")
        with pytest.raises(ValueError, match="YAMLコードブロックが見つかりません"):
            load_feeds(feed_md)


class TestSaveFeeds:
    def test_creates_file(self, tmp_path):
        feed_md = tmp_path / "new_feed.md"
        save_feeds({"feeds": []}, feed_md)
        assert feed_md.exists()

    def test_save_unicode(self, tmp_path):
        feed_md = tmp_path / "feed.md"
        data = {"feeds": [{"url": "https://example.com", "title": "日本語フィード"}]}
        save_feeds(data, feed_md)
        content = feed_md.read_text(encoding="utf-8")
        assert "日本語フィード" in content

    def test_saves_markdown_yaml_block(self, tmp_path):
        feed_md = tmp_path / "feed.md"
        save_feeds({"feeds": []}, feed_md)
        content = feed_md.read_text(encoding="utf-8")
        assert content.startswith("```yaml\n")
        assert content.endswith("```\n")


class TestImportance:
    def test_default_when_missing(self):
        assert feed_importance({}) == "normal"

    def test_valid_values_pass_through(self):
        assert feed_importance({"importance": "high"}) == "high"
        assert feed_importance({"importance": "normal"}) == "normal"
        assert feed_importance({"importance": "low"}) == "low"

    def test_case_insensitive_and_trimmed(self):
        assert feed_importance({"importance": " HIGH "}) == "high"

    def test_invalid_falls_back_to_default(self):
        assert feed_importance({"importance": "urgent"}) == "normal"

    def test_non_string_falls_back_to_default(self):
        assert normalize_importance(123) == "normal"
        assert normalize_importance(None) == "normal"

    def test_roundtrip_via_yaml(self, tmp_path):
        data = {"feeds": [{"url": "https://example.com/rss", "importance": "low"}]}
        feed_md = tmp_path / "feed.md"
        save_feeds(data, feed_md)
        loaded = load_feeds(feed_md)
        assert feed_importance(loaded["feeds"][0]) == "low"


class TestParseLastFetched:
    def test_iso_with_timezone(self):
        from datetime import datetime, timezone
        result = parse_last_fetched({"last_fetched": "2026-03-10T00:00:00+00:00"})
        assert result == datetime(2026, 3, 10, 0, 0, 0, tzinfo=timezone.utc)

    def test_iso_without_timezone_assumes_utc(self):
        from datetime import datetime, timezone
        result = parse_last_fetched({"last_fetched": "2026-03-10T00:00:00"})
        assert result == datetime(2026, 3, 10, 0, 0, 0, tzinfo=timezone.utc)

    def test_non_utc_timezone_normalized(self):
        from datetime import datetime, timezone, timedelta
        result = parse_last_fetched({"last_fetched": "2026-03-10T09:00:00+09:00"})
        assert result == datetime(2026, 3, 10, 0, 0, 0, tzinfo=timezone.utc)

    def test_missing_returns_none(self):
        assert parse_last_fetched({}) is None

    def test_empty_string_returns_none(self):
        assert parse_last_fetched({"last_fetched": ""}) is None

    def test_invalid_format_returns_none(self):
        assert parse_last_fetched({"last_fetched": "not-a-date"}) is None
