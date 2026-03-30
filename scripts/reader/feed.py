from datetime import datetime, timezone
from pathlib import Path

import yaml

from .config import get_feed_yaml


def load_feeds(feed_yaml: Path | None = None) -> dict:
    path = feed_yaml or get_feed_yaml()
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_feeds(data: dict, feed_yaml: Path | None = None):
    path = feed_yaml or get_feed_yaml()
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def parse_last_fetched(feed_info: dict) -> datetime | None:
    """feed_info の last_fetched を UTC の datetime に変換して返す。

    未設定やフォーマット不正の場合は None を返す。
    naive datetime の場合は UTC を付与し、aware の場合は UTC に正規化する。
    """
    raw = feed_info.get("last_fetched")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
