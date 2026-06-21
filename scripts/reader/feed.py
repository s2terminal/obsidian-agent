import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from reader.config import get_feed_md

_YAML_BLOCK_PATTERN = re.compile(r"```yaml\r?\n(.*?)\r?\n?```", re.DOTALL)

# フィードの重要度レベル
IMPORTANCE_HIGH = "high"      # 常に詳細（箇条書き）で要約する
IMPORTANCE_NORMAL = "normal"  # 記事内容から要約形式を自動判定する（デフォルト）
IMPORTANCE_LOW = "low"        # 詳細な要約はせず、常に一文で簡潔に要約する
DEFAULT_IMPORTANCE = IMPORTANCE_NORMAL
_VALID_IMPORTANCE = {IMPORTANCE_HIGH, IMPORTANCE_NORMAL, IMPORTANCE_LOW}


def normalize_importance(value: object) -> str:
    """重要度の値を既知のレベルに正規化する。不正値・未設定はデフォルトを返す。"""
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _VALID_IMPORTANCE:
            return normalized
    return DEFAULT_IMPORTANCE


def feed_importance(feed_info: dict) -> str:
    """フィード設定から正規化済みの重要度レベルを返す。"""
    return normalize_importance(feed_info.get("importance"))


def feed_id(feed_info: dict) -> str | None:
    """フィード設定dictからIDキー（値がNoneのキー）を返す。"""
    return next((k for k, v in feed_info.items() if v is None), None)


def load_feeds(feed_md: Path | None = None) -> dict:
    path = feed_md or get_feed_md()
    content = path.read_text(encoding="utf-8")
    match = _YAML_BLOCK_PATTERN.search(content)
    if not match:
        raise ValueError(f"YAMLコードブロックが見つかりません: {path}")
    return yaml.safe_load(match.group(1))


def save_feeds(data: dict, feed_md: Path | None = None):
    path = feed_md or get_feed_md()
    yaml_content = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    yaml_content = re.sub(r": null\n", ":\n", yaml_content)
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
