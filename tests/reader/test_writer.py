from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from reader.writer import render_news, write_news

JST = ZoneInfo("Asia/Tokyo")


class TestWriteNews:
    def _make_article(self, title="Article", link="https://example.com",
                      summary="- point 1", published="2026/03/30",
                      feed_title="Feed", feed_link="https://feed.example.com"):
        return {
            "title": title, "link": link, "summary": summary,
            "published": published, "feed_title": feed_title, "feed_link": feed_link,
        }

    def test_render_news_returns_markdown(self):
        articles = [self._make_article()]

        content = render_news(articles)

        assert content == (
            "## 2026/03/30\n\n"
            "### [Feed](https://feed.example.com)\n\n"
            "#### [Article](https://example.com)\n\n"
            "- point 1\n"
        )

    @patch("reader.writer.get_timezone", return_value=JST)
    @patch("reader.writer.datetime")
    def test_creates_new_file(self, mock_dt, _mock_tz, tmp_path):
        mock_dt.now.return_value = datetime(2026, 3, 30, tzinfo=JST)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        articles = [self._make_article()]
        write_news(articles, feed_out_dir=tmp_path)

        md_path = tmp_path / "2026" / "03-30.md"
        assert md_path.exists()
        content = md_path.read_text(encoding="utf-8")
        assert "## 2026/03/30" in content
        assert "### [Feed](https://feed.example.com)" in content
        assert "#### [Article](https://example.com)" in content
        assert "- point 1" in content

    @patch("reader.writer.get_timezone", return_value=JST)
    @patch("reader.writer.datetime")
    def test_appends_to_existing(self, mock_dt, _mock_tz, tmp_path):
        mock_dt.now.return_value = datetime(2026, 3, 30, tzinfo=JST)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        md_path = tmp_path / "2026" / "03-30.md"
        md_path.parent.mkdir(parents=True)
        md_path.write_text("## 2026/03/29\n\nOld content", encoding="utf-8")

        articles = [self._make_article()]
        write_news(articles, feed_out_dir=tmp_path)

        content = md_path.read_text(encoding="utf-8")
        assert "Old content" in content
        assert "## 2026/03/30" in content

    @patch("reader.writer.get_timezone", return_value=JST)
    @patch("reader.writer.datetime")
    def test_groups_by_feed(self, mock_dt, _mock_tz, tmp_path):
        mock_dt.now.return_value = datetime(2026, 3, 30, tzinfo=JST)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        articles = [
            self._make_article(title="A1", feed_title="Feed A", feed_link="https://a.com"),
            self._make_article(title="A2", feed_title="Feed A", feed_link="https://a.com"),
            self._make_article(title="B1", feed_title="Feed B", feed_link="https://b.com"),
        ]
        write_news(articles, feed_out_dir=tmp_path)

        content = (tmp_path / "2026" / "03-30.md").read_text(encoding="utf-8")
        assert "### [Feed A](https://a.com)" in content
        assert "### [Feed B](https://b.com)" in content
        assert content.count("#### [A1]") == 1
        assert content.count("#### [A2]") == 1
        assert content.count("#### [B1]") == 1

    @patch("reader.writer.get_timezone", return_value=JST)
    @patch("reader.writer.datetime")
    def test_uses_configured_timezone_for_filename(self, mock_dt, _mock_tz, tmp_path):
        """JST 3/31 01:00（UTC 3/30 16:00）のときファイル名は 03-31 になる"""

        # datetime(...) コンストラクタ呼び出しは本物を使う
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        # datetime.now(tz=...) の tz に応じて返す値を変える
        def now_side_effect(tz=None):
            # システム時刻（UTC）としては 2026-03-30 16:00:00+00:00
            if tz is None:
                return datetime(2026, 3, 30, 16, 0, 0, tzinfo=ZoneInfo("UTC"))
            # write_news 側が JST を使っていることをアサートする
            assert tz == JST
            # JST としては 2026-03-31 01:00:00+09:00
            return datetime(2026, 3, 31, 1, 0, 0, tzinfo=JST)

        mock_dt.now.side_effect = now_side_effect
        articles = [self._make_article()]
        write_news(articles, feed_out_dir=tmp_path)

        assert (tmp_path / "2026" / "03-31.md").exists()
