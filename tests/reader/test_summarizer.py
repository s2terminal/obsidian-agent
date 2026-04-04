from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reader.summarizer import summarize


class TestSummarize:
    @pytest.mark.asyncio
    async def test_returns_text(self):
        # Mock runner
        mock_runner = MagicMock()
        mock_session = MagicMock()
        mock_session.id = "session-1"
        mock_runner.session_service.create_session = AsyncMock(return_value=mock_session)

        # Mock event with text response
        mock_part = MagicMock()
        mock_part.text = "- 要約ポイント1\n- 要約ポイント2"
        mock_event = MagicMock()
        mock_event.content.parts = [mock_part]

        async def mock_run_async(**kwargs):
            yield mock_event

        mock_runner.run_async = mock_run_async

        result = await summarize(mock_runner, "Test Title", "Test content body")
        assert "要約ポイント1" in result
        assert "要約ポイント2" in result

    @pytest.mark.asyncio
    async def test_concatenates_multiple_events(self):
        mock_runner = MagicMock()
        mock_session = MagicMock()
        mock_session.id = "session-1"
        mock_runner.session_service.create_session = AsyncMock(return_value=mock_session)

        mock_part1 = MagicMock()
        mock_part1.text = "- ポイント1"
        mock_event1 = MagicMock()
        mock_event1.content.parts = [mock_part1]

        mock_part2 = MagicMock()
        mock_part2.text = "\n- ポイント2"
        mock_event2 = MagicMock()
        mock_event2.content.parts = [mock_part2]

        async def mock_run_async(**kwargs):
            yield mock_event1
            yield mock_event2

        mock_runner.run_async = mock_run_async

        result = await summarize(mock_runner, "Title", "Content")
        assert "ポイント1" in result
        assert "ポイント2" in result

    @pytest.mark.asyncio
    async def test_skips_events_without_content(self):
        mock_runner = MagicMock()
        mock_session = MagicMock()
        mock_session.id = "session-1"
        mock_runner.session_service.create_session = AsyncMock(return_value=mock_session)

        # Event with no content
        mock_event_empty = MagicMock()
        mock_event_empty.content = None

        # Event with content
        mock_part = MagicMock()
        mock_part.text = "- 要約"
        mock_event_good = MagicMock()
        mock_event_good.content.parts = [mock_part]

        async def mock_run_async(**kwargs):
            yield mock_event_empty
            yield mock_event_good

        mock_runner.run_async = mock_run_async

        result = await summarize(mock_runner, "Title", "Content")
        assert result == "- 要約"


class TestSummarizeLangfuse:
    @pytest.mark.asyncio
    async def test_traces_input_and_output(self):
        mock_runner = MagicMock()
        mock_session = MagicMock()
        mock_session.id = "session-1"
        mock_runner.session_service.create_session = AsyncMock(return_value=mock_session)

        mock_part = MagicMock()
        mock_part.text = "- 要約ポイント"
        mock_event = MagicMock()
        mock_event.content.parts = [mock_part]

        async def mock_run_async(**kwargs):
            yield mock_event

        mock_runner.run_async = mock_run_async

        mock_langfuse = MagicMock()
        with patch("reader.summarizer.get_client", return_value=mock_langfuse):
            result = await summarize(mock_runner, "テストタイトル", "テストコンテンツ")

        assert result == "- 要約ポイント"

        calls = mock_langfuse.update_current_generation.call_args_list
        assert len(calls) == 2

        # 1回目の呼び出し: 入力メッセージとモデル名
        first_kwargs = calls[0].kwargs
        assert "テストタイトル" in first_kwargs["input"]
        assert "テストコンテンツ" in first_kwargs["input"]
        assert first_kwargs["model"] == "gemini-3-flash-preview"

        # 2回目の呼び出し: 出力テキスト
        second_kwargs = calls[1].kwargs
        assert second_kwargs["output"] == "- 要約ポイント"

    @pytest.mark.asyncio
    async def test_succeeds_when_langfuse_unavailable(self):
        mock_runner = MagicMock()
        mock_session = MagicMock()
        mock_session.id = "session-1"
        mock_runner.session_service.create_session = AsyncMock(return_value=mock_session)

        mock_part = MagicMock()
        mock_part.text = "- 要約ポイント"
        mock_event = MagicMock()
        mock_event.content.parts = [mock_part]

        async def mock_run_async(**kwargs):
            yield mock_event

        mock_runner.run_async = mock_run_async

        # get_client() が例外を発生させてもsummarize()は正常に動作すること
        with patch("reader.summarizer.get_client", side_effect=RuntimeError("Langfuse unavailable")):
            result = await summarize(mock_runner, "テストタイトル", "テストコンテンツ")

        assert result == "- 要約ポイント"
