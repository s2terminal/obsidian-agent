from datetime import datetime, timezone
from unittest.mock import patch

from reader.writer import write_news


class TestWriteNews:
    def _make_article(self, title="Article", link="https://example.com",
                      summary="- point 1", published="2026/03/30",
                      feed_title="Feed", feed_link="https://feed.example.com"):
        return {
            "title": title, "link": link, "summary": summary,
            "published": published, "feed_title": feed_title, "feed_link": feed_link,
        }

    @patch("reader.writer.datetime")
    def test_creates_new_file(self, mock_dt, tmp_path):
        mock_dt.now.return_value = datetime(2026, 3, 30, tzinfo=timezone.utc)
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

    @patch("reader.writer.datetime")
    def test_appends_to_existing(self, mock_dt, tmp_path):
        mock_dt.now.return_value = datetime(2026, 3, 30, tzinfo=timezone.utc)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        md_path = tmp_path / "2026" / "03-30.md"
        md_path.parent.mkdir(parents=True)
        md_path.write_text("## 2026/03/29\n\nOld content", encoding="utf-8")

        articles = [self._make_article()]
        write_news(articles, feed_out_dir=tmp_path)

        content = md_path.read_text(encoding="utf-8")
        assert "Old content" in content
        assert "## 2026/03/30" in content

    @patch("reader.writer.datetime")
    def test_groups_by_feed(self, mock_dt, tmp_path):
        mock_dt.now.return_value = datetime(2026, 3, 30, tzinfo=timezone.utc)
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
