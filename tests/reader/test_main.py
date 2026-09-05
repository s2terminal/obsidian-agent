from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

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
        save_status = MagicMock()
        notify_slack = MagicMock()

        monkeypatch.setattr(main_module, "load_feeds", lambda: feeds_data)
        monkeypatch.setattr(main_module, "App", MagicMock(return_value=MagicMock()))
        monkeypatch.setattr(main_module, "InMemoryRunner", MagicMock(return_value=MagicMock()))
        monkeypatch.setattr(main_module, "process_feed", AsyncMock(return_value=(articles, [])))
        monkeypatch.setattr(main_module, "render_news", render_news)
        monkeypatch.setattr(main_module, "write_news", write_news)
        monkeypatch.setattr(main_module, "save_status", save_status)
        monkeypatch.setattr(main_module, "notify_slack", notify_slack)

        await main_module.main(summarize_only=True)

        captured = capsys.readouterr()
        assert "## 2026/03/30" in captured.out
        assert "要約のみモード" in captured.out
        render_news.assert_called_once_with(articles)
        write_news.assert_not_called()
        save_status.assert_not_called()
        notify_slack.assert_not_called()
        assert feeds_data["feeds"][0]["last_fetched"] == "2026-03-01T00:00:00+00:00"

    @pytest.mark.asyncio
    async def test_notifies_slack_with_obsidian_link_when_articles_added(self, monkeypatch):
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

        save_status = MagicMock()
        notify_slack = MagicMock()

        monkeypatch.setattr(main_module, "load_feeds", lambda: feeds_data)
        monkeypatch.setattr(main_module, "App", MagicMock(return_value=MagicMock()))
        monkeypatch.setattr(main_module, "InMemoryRunner", MagicMock(return_value=MagicMock()))
        monkeypatch.setattr(main_module, "process_feed", AsyncMock(return_value=(articles, [])))
        monkeypatch.setattr(main_module, "write_news", MagicMock(return_value=Path("/vault/ai-generated/feed/2026/03-30.md")))
        monkeypatch.setattr(main_module, "get_feed_out_dir", MagicMock(return_value=Path("/vault/ai-generated/feed")))
        monkeypatch.setattr(main_module, "save_status", save_status)
        monkeypatch.setattr(main_module, "notify_slack", notify_slack)

        await main_module.main(summarize_only=False)

        save_status.assert_called_once_with(feeds_data)
        notify_slack.assert_called_once()
        sent_message = notify_slack.call_args[0][0]
        assert "ai-generated/feed/ に 1件の記事を追加しました" in sent_message
        assert "obsidian://open?vault=RemoteVault&file=ai-generated/feed/2026/03-30.md" in sent_message

    @pytest.mark.asyncio
    async def test_inactive_feed_is_skipped(self, monkeypatch):
        feeds_data = {
            "feeds": [
                {"url": "https://example.com/feed", "active": False},
            ]
        }
        process_feed = AsyncMock()

        monkeypatch.setattr(main_module, "load_feeds", lambda: feeds_data)
        monkeypatch.setattr(main_module, "App", MagicMock(return_value=MagicMock()))
        monkeypatch.setattr(main_module, "InMemoryRunner", MagicMock(return_value=MagicMock()))
        monkeypatch.setattr(main_module, "process_feed", process_feed)
        monkeypatch.setattr(main_module, "notify_slack", MagicMock())

        await main_module.main(summarize_only=False)

        process_feed.assert_not_called()

    @pytest.mark.asyncio
    async def test_format_errors_included_in_slack_notification(self, monkeypatch):
        feeds_data = {
            "feeds": [
                {"url": "https://example.com/notes.md.txt"},
            ]
        }
        error_msg = "日付セクションが見つかりません（フォーマット不正の可能性）: https://example.com/notes.md.txt"
        notify_slack = MagicMock()

        monkeypatch.setattr(main_module, "load_feeds", lambda: feeds_data)
        monkeypatch.setattr(main_module, "App", MagicMock(return_value=MagicMock()))
        monkeypatch.setattr(main_module, "InMemoryRunner", MagicMock(return_value=MagicMock()))
        monkeypatch.setattr(main_module, "process_feed", AsyncMock(return_value=([], [error_msg])))
        monkeypatch.setattr(main_module, "notify_slack", notify_slack)

        await main_module.main(summarize_only=False)

        notify_slack.assert_called_once()
        sent_message = notify_slack.call_args[0][0]
        assert ":warning: フォーマットエラー:" in sent_message
        assert error_msg in sent_message

    @pytest.mark.asyncio
    async def test_format_errors_included_even_when_articles_exist(self, monkeypatch):
        feeds_data = {
            "feeds": [
                {"url": "https://example.com/feed"},
                {"url": "https://example.com/notes.md.txt"},
            ]
        }
        articles = [
            {
                "title": "Article 1", "link": "https://example.com/1",
                "summary": "- 要約", "published": "2026/03/30",
                "feed_title": "Feed", "feed_link": "https://example.com/feed",
            }
        ]
        error_msg = "日付セクションが見つかりません（フォーマット不正の可能性）: https://example.com/notes.md.txt"
        notify_slack = MagicMock()

        monkeypatch.setattr(main_module, "load_feeds", lambda: feeds_data)
        monkeypatch.setattr(main_module, "App", MagicMock(return_value=MagicMock()))
        monkeypatch.setattr(main_module, "InMemoryRunner", MagicMock(return_value=MagicMock()))
        monkeypatch.setattr(
            main_module, "process_feed",
            AsyncMock(side_effect=[(articles, []), ([], [error_msg])])
        )
        monkeypatch.setattr(main_module, "write_news", MagicMock(return_value=Path("/vault/ai-generated/feed/2026/03-30.md")))
        monkeypatch.setattr(main_module, "get_feed_out_dir", MagicMock(return_value=Path("/vault/ai-generated/feed")))
        monkeypatch.setattr(main_module, "save_status", MagicMock())
        monkeypatch.setattr(main_module, "notify_slack", notify_slack)

        await main_module.main(summarize_only=False)

        notify_slack.assert_called_once()
        sent_message = notify_slack.call_args[0][0]
        assert "1件の記事を追加しました" in sent_message
        assert ":warning: フォーマットエラー:" in sent_message
        assert error_msg in sent_message


@pytest.mark.parametrize("write_fails", [False, True])
async def test_real_storage_updates_only_successful_feed(tmp_path, monkeypatch, write_fails):
    import yaml

    config = tmp_path / "feed.md"
    config.write_text("# 設定を保持\n```yaml\nfeeds:\n- url: a\n- url: b\n- url: c\n  active: false\n```\n")
    original = config.read_bytes()
    monkeypatch.setenv("OBSIDIAN_ROOT", str(tmp_path.parent))
    monkeypatch.setenv("OBSIDIAN_AGENT_DIR", tmp_path.name)
    monkeypatch.setattr(main_module, "App", MagicMock())
    monkeypatch.setattr(main_module, "InMemoryRunner", MagicMock())
    monkeypatch.setattr(main_module, "process_feed", AsyncMock(side_effect=[([{"title": "記事"}], []), ([], [])]))
    monkeypatch.setattr(main_module, "write_news", MagicMock(
        side_effect=OSError("書き込み失敗") if write_fails else None,
        return_value=tmp_path / "output.md",
    ))
    monkeypatch.setattr(main_module, "get_feed_out_dir", lambda: tmp_path)
    monkeypatch.setattr(main_module, "notify_slack", MagicMock())
    if write_fails:
        with pytest.raises(OSError):
            await main_module.main()
        assert not (tmp_path / "status.yaml").exists()
    else:
        await main_module.main()
        status = yaml.safe_load((tmp_path / "status.yaml").read_text())
        assert set(status["feeds"]) == {"a"}
        assert main_module.parse_last_fetched(status["feeds"]["a"]) is not None
    assert config.read_bytes() == original
