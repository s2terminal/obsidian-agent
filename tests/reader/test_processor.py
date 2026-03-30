from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reader.cache import cache_path


class TestProcessFeed:
    """process_feed のテスト。feedparser と summarize をモックして検証する。"""

    @pytest.fixture(autouse=True)
    def setup_cache_dir(self, tmp_path, monkeypatch):
        """キャッシュディレクトリを tmp_path に差し替える。"""
        self.cache_dir = tmp_path / "cache"
        self.cache_dir.mkdir()
        monkeypatch.setattr("reader.cache.CACHE_DIR", self.cache_dir)
        monkeypatch.setattr("reader.main.load_cache", lambda url: self._load_cache(url))
        monkeypatch.setattr("reader.main.save_cache", lambda url, cache: self._save_cache(url, cache))
        self._caches: dict[str, dict] = {}

    def _load_cache(self, url):
        from reader.cache import load_cache
        return load_cache(url, self.cache_dir)

    def _save_cache(self, url, cache):
        from reader.cache import save_cache
        save_cache(url, cache, self.cache_dir)

    def _make_entry(self, eid="e1", title="Test Article", link="https://example.com/1",
                    summary="Article content"):
        return {"id": eid, "title": title, "link": link, "summary": summary}

    def _make_feed_result(self, entries, bozo=False, feed_title="Test Feed", feed_link="https://example.com"):
        feed = MagicMock()
        feed.bozo = bozo
        feed.entries = entries
        feed.feed.title = feed_title
        feed.feed.link = feed_link
        return feed

    @pytest.mark.asyncio
    @patch("reader.main.summarize", new_callable=AsyncMock)
    @patch("reader.main.feedparser.parse")
    async def test_new_articles(self, mock_parse, mock_summarize):
        mock_parse.return_value = self._make_feed_result([
            self._make_entry("e1", "Article 1"),
            self._make_entry("e2", "Article 2"),
        ])
        mock_summarize.return_value = "- 要約"

        from reader.main import process_feed
        runner = MagicMock()
        result = await process_feed(runner, {"url": "https://example.com/feed"})

        assert len(result) == 2
        assert result[0]["title"] == "Article 1"
        assert result[1]["title"] == "Article 2"
        assert mock_summarize.call_count == 2

    @pytest.mark.asyncio
    @patch("reader.main.summarize", new_callable=AsyncMock)
    @patch("reader.main.feedparser.parse")
    async def test_skips_done(self, mock_parse, mock_summarize, tmp_path):
        # Pre-populate cache with done entry
        from reader.cache import save_cache
        save_cache("https://example.com/feed", {"e1": {"status": "done"}}, self.cache_dir)

        mock_parse.return_value = self._make_feed_result([
            self._make_entry("e1", "Already Done"),
            self._make_entry("e2", "New Article"),
        ])
        mock_summarize.return_value = "- 新しい要約"

        from reader.main import process_feed
        runner = MagicMock()
        result = await process_feed(runner, {"url": "https://example.com/feed"})

        assert len(result) == 1
        assert result[0]["title"] == "New Article"

    @pytest.mark.asyncio
    @patch("reader.main.summarize", new_callable=AsyncMock)
    @patch("reader.main.feedparser.parse")
    async def test_skips_skipped(self, mock_parse, mock_summarize):
        from reader.cache import save_cache
        save_cache("https://example.com/feed", {"e1": {"status": "skipped"}}, self.cache_dir)

        mock_parse.return_value = self._make_feed_result([
            self._make_entry("e1", "Skipped Article"),
        ])

        from reader.main import process_feed
        runner = MagicMock()
        result = await process_feed(runner, {"url": "https://example.com/feed"})

        assert len(result) == 0
        mock_summarize.assert_not_called()

    @pytest.mark.asyncio
    @patch("reader.main.summarize", new_callable=AsyncMock)
    @patch("reader.main.feedparser.parse")
    async def test_retries_pending(self, mock_parse, mock_summarize):
        from reader.cache import save_cache
        save_cache("https://example.com/feed", {
            "e1": {
                "status": "pending",
                "title": "Pending Title",
                "link": "https://example.com/pending",
                "content": "Pending content",
                "published": "2026/03/29",
            }
        }, self.cache_dir)

        mock_parse.return_value = self._make_feed_result([
            self._make_entry("e1"),
        ])
        mock_summarize.return_value = "- リトライ要約"

        from reader.main import process_feed
        runner = MagicMock()
        result = await process_feed(runner, {"url": "https://example.com/feed"})

        assert len(result) == 1
        assert result[0]["title"] == "Pending Title"
        assert result[0]["summary"] == "- リトライ要約"

    @pytest.mark.asyncio
    @patch("reader.main.summarize", new_callable=AsyncMock)
    @patch("reader.main.feedparser.parse")
    async def test_respects_max_articles(self, mock_parse, mock_summarize):
        entries = [self._make_entry(f"e{i}", f"Article {i}") for i in range(10)]
        mock_parse.return_value = self._make_feed_result(entries)
        mock_summarize.return_value = "- 要約"

        from reader.main import process_feed
        runner = MagicMock()
        result = await process_feed(runner, {"url": "https://example.com/feed", "max_articles": 2})

        assert len(result) == 2
        assert mock_summarize.call_count == 2

    @pytest.mark.asyncio
    @patch("reader.main.summarize", new_callable=AsyncMock)
    @patch("reader.main.feedparser.parse")
    async def test_summarize_error_sets_pending(self, mock_parse, mock_summarize):
        mock_parse.return_value = self._make_feed_result([
            self._make_entry("e1", "Fail Article"),
        ])
        mock_summarize.side_effect = Exception("API Error")

        from reader.main import process_feed
        runner = MagicMock()
        result = await process_feed(runner, {"url": "https://example.com/feed"})

        assert len(result) == 0

        # Check that the cache was saved with pending status
        from reader.cache import load_cache
        cache = load_cache("https://example.com/feed", self.cache_dir)
        assert cache["e1"]["status"] == "pending"
        assert cache["e1"]["title"] == "Fail Article"

    @pytest.mark.asyncio
    @patch("reader.main.feedparser.parse")
    async def test_bozo_feed_with_no_entries(self, mock_parse):
        feed = self._make_feed_result([], bozo=True)
        mock_parse.return_value = feed

        from reader.main import process_feed
        runner = MagicMock()
        result = await process_feed(runner, {"url": "https://example.com/broken"})

        assert result == []

    @pytest.mark.asyncio
    @patch("reader.main.summarize", new_callable=AsyncMock)
    @patch("reader.main.feedparser.parse")
    async def test_skips_old_articles_by_last_fetched(self, mock_parse, mock_summarize):
        """last_fetched より古い記事はスキップされる。"""
        from time import struct_time

        old_entry = self._make_entry("e1", "Old Article")
        old_entry["published_parsed"] = struct_time((2026, 3, 1, 0, 0, 0, 0, 0, 0))

        new_entry = self._make_entry("e2", "New Article")
        new_entry["published_parsed"] = struct_time((2026, 3, 20, 0, 0, 0, 0, 0, 0))

        mock_parse.return_value = self._make_feed_result([old_entry, new_entry])
        mock_summarize.return_value = "- 要約"

        from reader.main import process_feed
        runner = MagicMock()
        result = await process_feed(runner, {
            "url": "https://example.com/feed",
            "last_fetched": "2026-03-10T00:00:00+00:00",
        })

        assert len(result) == 1
        assert result[0]["title"] == "New Article"
        assert mock_summarize.call_count == 1

    @pytest.mark.asyncio
    @patch("reader.main.summarize", new_callable=AsyncMock)
    @patch("reader.main.feedparser.parse")
    async def test_no_last_fetched_processes_all(self, mock_parse, mock_summarize):
        """last_fetched が設定されていない場合は全記事を処理する。"""
        from time import struct_time

        entry = self._make_entry("e1", "Article")
        entry["published_parsed"] = struct_time((2020, 1, 1, 0, 0, 0, 0, 0, 0))

        mock_parse.return_value = self._make_feed_result([entry])
        mock_summarize.return_value = "- 要約"

        from reader.main import process_feed
        runner = MagicMock()
        result = await process_feed(runner, {"url": "https://example.com/feed"})

        assert len(result) == 1

    @pytest.mark.asyncio
    @patch("reader.main.summarize", new_callable=AsyncMock)
    @patch("reader.main.feedparser.parse")
    async def test_pending_retried_even_if_older_than_last_fetched(self, mock_parse, mock_summarize):
        """pending 記事は last_fetched より古くてもリトライされる。"""
        from reader.cache import save_cache
        save_cache("https://example.com/feed", {
            "e1": {
                "status": "pending",
                "title": "Old Pending",
                "link": "https://example.com/old",
                "content": "Old content",
                "published": "2026/01/01",
            }
        }, self.cache_dir)

        from time import struct_time
        entry = self._make_entry("e1")
        entry["published_parsed"] = struct_time((2026, 1, 1, 0, 0, 0, 0, 0, 0))

        mock_parse.return_value = self._make_feed_result([entry])
        mock_summarize.return_value = "- リトライ要約"

        from reader.main import process_feed
        runner = MagicMock()
        result = await process_feed(runner, {
            "url": "https://example.com/feed",
            "last_fetched": "2026-03-01T00:00:00+00:00",
        })

        assert len(result) == 1
        assert result[0]["title"] == "Old Pending"

    @pytest.mark.asyncio
    @patch("reader.main.summarize", new_callable=AsyncMock)
    @patch("reader.main.feedparser.parse")
    async def test_articles_without_date_not_skipped(self, mock_parse, mock_summarize):
        """投稿日が無い記事は last_fetched があってもスキップされない。"""
        entry = self._make_entry("e1", "No Date Article")
        # published_parsed も updated_parsed も無い

        mock_parse.return_value = self._make_feed_result([entry])
        mock_summarize.return_value = "- 要約"

        from reader.main import process_feed
        runner = MagicMock()
        result = await process_feed(runner, {
            "url": "https://example.com/feed",
            "last_fetched": "2026-03-01T00:00:00+00:00",
        })

        assert len(result) == 1
