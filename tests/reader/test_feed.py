import pytest
import yaml

from reader.config import get_obsidian_agent_dir
from reader.feed import feed_id, feed_importance, load_feeds, normalize_importance, parse_last_fetched, save_status


def write_config(directory, feeds):
    path = directory / "feed.md"
    path.write_text("# 購読設定\n\n```yaml\n# 人間のコメント\n" + yaml.safe_dump({"feeds": feeds}, allow_unicode=True) + "```\n\n自由なメモ\n")
    return path


def test_missing_status_and_environment(tmp_path, monkeypatch):
    write_config(tmp_path, [{"url": "a", "myblog": None, "importance": "low"}])
    monkeypatch.setenv("OBSIDIAN_ROOT", str(tmp_path.parent))
    monkeypatch.setenv("OBSIDIAN_AGENT_DIR", tmp_path.name)
    assert get_obsidian_agent_dir() == tmp_path
    feed = load_feeds()["feeds"][0]
    assert "last_fetched" not in feed
    assert feed_id(feed) == "myblog"
    assert not (tmp_path / "status.yaml").exists()


def test_save_preserves_concurrent_config_edit_and_other_status(tmp_path):
    path = write_config(tmp_path, [{"url": "a"}, {"url": "b"}])
    save_status({"feeds": [{"url": "b", "last_fetched": "old"}]}, tmp_path)
    loaded = load_feeds(tmp_path)
    loaded["feeds"][0]["last_fetched"] = "new"
    write_config(tmp_path, [{"url": "b", "title": "変更"}, {"url": "a", "active": False}])
    original = path.read_bytes()
    save_status({"feeds": [loaded["feeds"][0]]}, tmp_path)
    assert path.read_bytes() == original
    assert load_feeds(tmp_path)["feeds"] == [
        {"url": "b", "title": "変更", "last_fetched": "old"},
        {"url": "a", "active": False, "last_fetched": "new"},
    ]
    assert yaml.safe_load((tmp_path / "status.yaml").read_text()) == {
        "feeds": {"b": {"last_fetched": "old"}, "a": {"last_fetched": "new"}},
        "raindrop": {}
    }


def test_changed_url_does_not_inherit_status(tmp_path):
    write_config(tmp_path, [{"url": "new"}])
    save_status({"feeds": [{"url": "old", "last_fetched": "old"}]}, tmp_path)
    assert load_feeds(tmp_path) == {"feeds": [{"url": "new"}]}


@pytest.mark.parametrize("feeds", [[{"url": "a"}, {"url": "a"}], [{}]])
def test_invalid_config(tmp_path, feeds):
    write_config(tmp_path, feeds)
    with pytest.raises(ValueError):
        load_feeds(tmp_path)


def test_non_mapping_status_is_not_overwritten(tmp_path):
    write_config(tmp_path, [{"url": "a"}])
    path = tmp_path / "status.yaml"
    path.write_text("- just a list\n")
    with pytest.raises(ValueError):
        save_status({"feeds": [{"url": "a", "last_fetched": "new"}]}, tmp_path)
    assert path.read_text() == "- just a list\n"


def test_malformed_namespace_is_treated_as_empty(tmp_path):
    write_config(tmp_path, [{"url": "a"}])
    (tmp_path / "status.yaml").write_text("feeds: []\n")
    save_status({"feeds": [{"url": "a", "last_fetched": "new"}]}, tmp_path)
    assert load_feeds(tmp_path)["feeds"][0]["last_fetched"] == "new"


def test_legacy_environment_rejects_file(tmp_path, monkeypatch):
    source = tmp_path / "feed.md"
    source.touch()
    monkeypatch.setenv("OBSIDIAN_ROOT", str(tmp_path))
    monkeypatch.setenv("OBSIDIAN_AGENT_DIR", source.name)
    with pytest.raises(ValueError, match="ディレクトリ"):
        load_feeds()


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


def test_failed_atomic_replace_preserves_status(tmp_path, monkeypatch):
    import reader.state as state_module

    save_status({"feeds": [{"url": "a", "last_fetched": "old"}]}, tmp_path)
    original = (tmp_path / "status.yaml").read_bytes()

    def fail_replace(*args):
        raise OSError("置換失敗")

    monkeypatch.setattr(state_module.os, "replace", fail_replace)
    with pytest.raises(OSError):
        save_status({"feeds": [{"url": "a", "last_fetched": "new"}]}, tmp_path)
    assert (tmp_path / "status.yaml").read_bytes() == original
    assert list(tmp_path.iterdir()) == [tmp_path / "status.yaml"]


def test_feed_dir_is_relative_to_vault_not_working_directory(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    directory = vault / "settings" / "feed"
    directory.mkdir(parents=True)
    write_config(directory, [{"url": "a"}])
    monkeypatch.setenv("OBSIDIAN_ROOT", str(vault))
    monkeypatch.setenv("OBSIDIAN_AGENT_DIR", "settings/feed")
    monkeypatch.chdir(tmp_path)
    assert get_obsidian_agent_dir() == directory
    assert load_feeds() == {"feeds": [{"url": "a"}]}
    save_status({"feeds": [{"url": "a", "last_fetched": "new"}]})
    assert (directory / "status.yaml").exists()


def test_feed_dir_rejects_absolute_path(tmp_path, monkeypatch):
    monkeypatch.setenv("OBSIDIAN_AGENT_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="相対パス"):
        get_obsidian_agent_dir()


@pytest.mark.parametrize("content", [
    "# 購読設定\n```yaml\nfeeds: []\n```\nメモ\n",
    "```yaml\r\nfeeds: []\r\n```\r\n",
    "```yaml\nfeeds: []```\n",
])
def test_markdown_yaml_block_formats(tmp_path, content):
    (tmp_path / "feed.md").write_bytes(content.encode("utf-8"))
    assert load_feeds(tmp_path) == {"feeds": []}


def test_missing_yaml_block(tmp_path):
    (tmp_path / "feed.md").write_text("# フィード設定\n")
    with pytest.raises(ValueError, match="YAMLコードブロック"):
        load_feeds(tmp_path)
