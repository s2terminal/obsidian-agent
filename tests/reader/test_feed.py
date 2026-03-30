import yaml

from reader.feed import load_feeds, parse_last_fetched, save_feeds


class TestLoadFeeds:
    def test_load(self, tmp_path):
        feed_yaml = tmp_path / "feed.yaml"
        data = {"feeds": [{"url": "https://example.com/rss", "max_articles": 3}]}
        feed_yaml.write_text(yaml.dump(data), encoding="utf-8")

        result = load_feeds(feed_yaml)
        assert result == data

    def test_roundtrip(self, tmp_path):
        feed_yaml = tmp_path / "feed.yaml"
        data = {
            "feeds": [
                {"url": "https://example.com/rss", "max_articles": 5},
                {"url": "https://other.com/atom", "last_fetched": "2026-03-30T00:00:00+00:00"},
            ]
        }
        save_feeds(data, feed_yaml)
        assert load_feeds(feed_yaml) == data


class TestSaveFeeds:
    def test_creates_file(self, tmp_path):
        feed_yaml = tmp_path / "new_feed.yaml"
        save_feeds({"feeds": []}, feed_yaml)
        assert feed_yaml.exists()

    def test_save_unicode(self, tmp_path):
        feed_yaml = tmp_path / "feed.yaml"
        data = {"feeds": [{"url": "https://example.com", "title": "日本語フィード"}]}
        save_feeds(data, feed_yaml)
        content = feed_yaml.read_text(encoding="utf-8")
        assert "日本語フィード" in content


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
