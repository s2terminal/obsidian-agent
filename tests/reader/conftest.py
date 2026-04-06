import itertools
import os
import re
from time import struct_time

import pytest
from _pytest.mark.expression import Expression

_IDENTIFIER_PATTERN = re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b")
_RESERVED_WORDS = {"and", "or", "not", "True", "False", "None"}


def _extract_marker_names(markexpr: str) -> set[str]:
    return {
        token
        for token in _IDENTIFIER_PATTERN.findall(markexpr)
        if token not in _RESERVED_WORDS
    }


def _should_enable_langfuse(markexpr: str) -> bool:
    markexpr = (markexpr or "").strip()
    if not markexpr:
        return False

    marker_names = sorted(_extract_marker_names(markexpr))
    if "llm_eval" not in marker_names:
        return False

    expression = Expression.compile(markexpr)
    other_markers = [name for name in marker_names if name != "llm_eval"]

    for values in itertools.product((False, True), repeat=len(other_markers)):
        assignments = dict(zip(other_markers, values, strict=True))
        assignments["llm_eval"] = True
        if expression.evaluate(lambda name, /, **kwargs: assignments.get(name, False)):
            return True

    return False


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
