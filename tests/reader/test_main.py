from unittest.mock import AsyncMock, MagicMock

import pytest

from reader import main as main_module


class TestMain:
    @pytest.mark.asyncio
    async def test_summarize_only_mode_prints_summary_without_side_effects(self, monkeypatch, capsys):
        feeds_data = {
            "feeds": [
                {
                    "url": "https://example.com/feed",
                    "last_fetched": "2026-03-01T00:00:00+00:00",
                }
            ]
        }
        articles = [
            {
                "title": "Article 1",
                "link": "https://example.com/1",
                "summary": "- 要約",
                "published": "2026/03/30",
                "feed_title": "Feed",
                "feed_link": "https://example.com/feed",
            }
        ]

        render_news = MagicMock(return_value="## 2026/03/30\n")
        write_news = MagicMock()
        save_feeds = MagicMock()
        notify_slack = MagicMock()

        monkeypatch.setattr(main_module, "load_feeds", lambda: feeds_data)
        monkeypatch.setattr(main_module, "InMemoryRunner", MagicMock(return_value=MagicMock()))
        monkeypatch.setattr(main_module, "process_feed", AsyncMock(return_value=articles))
        monkeypatch.setattr(main_module, "render_news", render_news)
        monkeypatch.setattr(main_module, "write_news", write_news)
        monkeypatch.setattr(main_module, "save_feeds", save_feeds)
        monkeypatch.setattr(main_module, "notify_slack", notify_slack)

        await main_module.main(summarize_only=True)

        captured = capsys.readouterr()
        assert "## 2026/03/30" in captured.out
        assert "要約のみモード" in captured.out
        render_news.assert_called_once_with(articles)
        write_news.assert_not_called()
        save_feeds.assert_not_called()
        notify_slack.assert_not_called()
        assert feeds_data["feeds"][0]["last_fetched"] == "2026-03-01T00:00:00+00:00"

    def test_build_parser_accepts_summarize_only(self):
        parser = main_module.build_parser()

        parsed = parser.parse_args(["--summarize-only"])
        assert parsed.summarize_only is True
