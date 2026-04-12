import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .config import get_feed_md

_YAML_BLOCK_PATTERN = re.compile(r"```yaml\r?\n(.*?)\r?\n```", re.DOTALL)


def load_feeds(feed_md: Path | None = None) -> dict:
    path = feed_md or get_feed_md()
    content = path.read_text(encoding="utf-8")
    match = _YAML_BLOCK_PATTERN.search(content)
    if not match:
        raise ValueError(f"YAMLコードブロックが見つかりません: {path}")
    return yaml.safe_load(match.group(1))


def save_feeds(data: dict, feed_md: Path | None = None):
    path = feed_md or get_feed_md()
    yaml_content = yaml.dump(data, default_flow_style=False, allow_unicode=True)
    if not yaml_content.endswith("\n"):
        yaml_content += "\n"
    path.write_text(f"```yaml\n{yaml_content}```\n", encoding="utf-8")


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
