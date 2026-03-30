import json

import pytest

from reader.cache import cache_path, load_cache, save_cache


class TestCachePath:
    def test_deterministic(self, tmp_path):
        url = "https://example.com/feed.xml"
        p1 = cache_path(url, tmp_path)
        p2 = cache_path(url, tmp_path)
        assert p1 == p2

    def test_different_urls(self, tmp_path):
        p1 = cache_path("https://example.com/a", tmp_path)
        p2 = cache_path("https://example.com/b", tmp_path)
        assert p1 != p2

    def test_json_extension(self, tmp_path):
        p = cache_path("https://example.com/feed.xml", tmp_path)
        assert p.suffix == ".json"


class TestLoadCache:
    def test_no_file_returns_empty(self, tmp_path):
        assert load_cache("https://no-such-feed.com", tmp_path) == {}

    def test_existing_file(self, tmp_path):
        url = "https://example.com/feed"
        data = {"entry-1": {"title": "t", "link": "l", "content": "c"}}
        p = cache_path(url, tmp_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data), encoding="utf-8")

        result = load_cache(url, tmp_path)
        assert result == data

    def test_legacy_list_format(self, tmp_path):
        url = "https://example.com/legacy"
        p = cache_path(url, tmp_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(["id-1", "id-2"]), encoding="utf-8")

        result = load_cache(url, tmp_path)
        assert result == {}

    def test_migrates_old_status_format(self, tmp_path):
        """旧形式の status 付きエントリを移行: done/skipped は除去、pending は status を除去。"""
        url = "https://example.com/migrate"
        data = {
            "e1": {"status": "done"},
            "e2": {"status": "skipped"},
            "e3": {"status": "pending", "title": "t", "link": "l", "content": "c"},
        }
        p = cache_path(url, tmp_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data), encoding="utf-8")

        result = load_cache(url, tmp_path)
        assert "e1" not in result
        assert "e2" not in result
        assert result == {"e3": {"title": "t", "link": "l", "content": "c"}}


class TestSaveCache:
    def test_creates_directory(self, tmp_path):
        cache_dir = tmp_path / "sub" / "dir"
        save_cache("https://example.com", {"e1": {"title": "t", "link": "l", "content": "c"}}, cache_dir)
        assert cache_dir.exists()

    def test_roundtrip(self, tmp_path):
        url = "https://example.com/feed"
        data = {"entry-1": {"title": "Test", "link": "l", "content": "c"}}
        save_cache(url, data, tmp_path)
        assert load_cache(url, tmp_path) == data
