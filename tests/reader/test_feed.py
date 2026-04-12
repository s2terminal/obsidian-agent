import pytest
import yaml

from reader.feed import load_feeds, parse_last_fetched, save_feeds

_YAML_BLOCK_TEMPLATE = "```yaml\n{yaml_content}```\n"


def _make_feed_md(tmp_path, name, data):
    feed_md = tmp_path / name
    yaml_content = yaml.dump(data, default_flow_style=False, allow_unicode=True)
    feed_md.write_text(_YAML_BLOCK_TEMPLATE.format(yaml_content=yaml_content), encoding="utf-8")
    return feed_md


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
                {"url": "https://example.com/rss", "max_articles": 5},
                {"url": "https://other.com/atom", "last_fetched": "2026-03-30T00:00:00+00:00"},
            ]
        }
        save_feeds(data, feed_md)
        assert load_feeds(feed_md) == data

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
