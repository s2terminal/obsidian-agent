import os
from time import struct_time

import pytest


def pytest_configure(config):
    # llm_eval マーカーを明示的に指定した場合はLangfuseを有効にする
    # それ以外（通常のテスト実行）ではLangfuseを無効化する
    # ※ Langfuse シングルトンが初期化される前に設定する必要があるため、フック内で設定する
    markexpr = getattr(config.option, "markexpr", "").strip()
    if markexpr != "llm_eval":
        os.environ.setdefault("LANGFUSE_TRACING_ENABLED", "false")


@pytest.fixture
def sample_articles():
    """テスト用の記事データリスト。"""
    return [
        {
            "title": "Article 1",
            "link": "https://example.com/1",
            "summary": "- 要約1\n- 要約2",
            "published": "2026/03/30",
            "feed_title": "Test Feed",
            "feed_link": "https://example.com/feed",
        },
        {
            "title": "Article 2",
            "link": "https://example.com/2",
            "summary": "- 要約3\n- 要約4",
            "published": "2026/03/30",
            "feed_title": "Test Feed",
            "feed_link": "https://example.com/feed",
        },
    ]


@pytest.fixture
def sample_entry():
    """feedparser エントリ風の dict。"""
    return {
        "id": "entry-001",
        "title": "Test Article",
        "link": "https://example.com/article",
        "summary": "This is the summary.",
        "published_parsed": struct_time((2026, 3, 15, 12, 0, 0, 6, 74, 0)),
    }
