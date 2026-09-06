"""各ソースの共通データ。表示日付は既存 RSS の表記を保持する。"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal


class SourceFetchError(Exception):
    """秘密情報を含まない取得エラー。"""


@dataclass(frozen=True)
class SourceArticle:
    id: str
    source_key: str
    source_type: Literal["rss", "markdown", "raindrop"]
    title: str
    link: str
    content: str | None
    content_kind: Literal["body", "excerpt", "none"]
    published_at: datetime | None
    saved_at: datetime | None
    display_date: str | None = None


@dataclass(frozen=True)
class RaindropCursor:
    last_fetched: datetime
    boundary_ids: frozenset[str]


@dataclass(frozen=True)
class FetchResult:
    articles: list[SourceArticle]
    source_title: str
    source_link: str
    next_cursor: RaindropCursor | None = None


def utc_datetime(value: object) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValueError('タイムゾーン付きのISO 8601日時が必要です') from None
    if parsed.tzinfo is None:
        raise ValueError('タイムゾーン付きのISO 8601日時が必要です')
    return parsed.astimezone(timezone.utc)


