import os
import re
from time import struct_time

import pytest

_LLM_EVAL_WORD_PATTERN = re.compile(r"\bllm_eval\b")
_LLM_EVAL_NEGATED_PATTERN = re.compile(r"\bnot\s+llm_eval\b")


def _should_enable_langfuse(markexpr: str) -> bool:
    """markexpr に llm_eval が（否定なしで）含まれるかを判定する。

    注: 内部APIを使わない簡易実装のため、複雑な論理式の正確な評価は行わない。
    典型的なユースケース（'llm_eval'、'llm_eval and X'、'not llm_eval'）に対応する。
    """
    markexpr = (markexpr or "").strip()
    if not markexpr:
        return False
    if not _LLM_EVAL_WORD_PATTERN.search(markexpr):
        return False
    if _LLM_EVAL_NEGATED_PATTERN.search(markexpr):
        return False
    return True


def pytest_configure(config):
    # llm_eval を含むマーカー式で実行する場合はLangfuseを有効化し、
    # それ以外は常に明示的に無効化する
    # ※ Langfuse シングルトンが初期化される前に設定する必要があるため、フック内で設定する
    markexpr = getattr(config.option, "markexpr", "")
    os.environ["LANGFUSE_TRACING_ENABLED"] = (
        "true" if _should_enable_langfuse(markexpr) else "false"
    )


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
