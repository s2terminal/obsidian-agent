import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from reader.config import get_obsidian_agent_dir


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


def validate_feeds(data: object) -> dict:
    """設定の構造と、状態の識別に用いるURLの一意性を確認する。"""
    if not isinstance(data, dict) or not isinstance(data.get("feeds"), list):
        raise ValueError("feedsにはリストを指定してください")
    urls = set()
    for feed in data["feeds"]:
        if not isinstance(feed, dict) or not isinstance(feed.get("url"), str) or not feed["url"].strip():
            raise ValueError("各フィードには空でないurlが必要です")
        if feed["url"] in urls:
            raise ValueError(f"フィードURLが重複しています: {feed['url']}")
        urls.add(feed["url"])
    return data


def _load_status(directory: Path) -> dict:
    path = directory / "status.yaml"
    if not path.exists():
        return {"feeds": {}}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("feeds"), dict):
        raise ValueError("status.yamlのfeedsにはURLをキーとするマッピングが必要です")
    if any(not isinstance(value, dict) for value in data["feeds"].values()):
        raise ValueError("status.yamlの各フィードの状態にはマッピングが必要です")
    return data


def load_feeds(feed_dir: Path | None = None) -> dict:
    """設定と状態をメモリ上で結合する。設定ファイルには書き込まない。"""
    directory = feed_dir or get_obsidian_agent_dir()
    path = directory / "feed.md"
    match = _YAML_BLOCK_PATTERN.search(path.read_text(encoding="utf-8"))
    if not match:
        raise ValueError(f"YAMLコードブロックが見つかりません: {path}")
    data = validate_feeds(yaml.safe_load(match.group(1)))
    status = _load_status(directory)
    for feed in data["feeds"]:
        state = status["feeds"].get(feed["url"], {})
        if "last_fetched" in state:
            feed["last_fetched"] = state["last_fetched"]
    return data


def _dump_yaml(data: dict) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def save_status(data: dict, feed_dir: Path | None = None) -> None:
    """取得時刻だけを保存する。一時ファイルの置換で書き込み途中の破損を防ぐ。"""
    validate_feeds(data)
    directory = feed_dir or get_obsidian_agent_dir()
    status = _load_status(directory)
    for feed in data["feeds"]:
        if "last_fetched" in feed:
            status["feeds"].setdefault(feed["url"], {})["last_fetched"] = feed["last_fetched"]
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(_dump_yaml(status))
        os.replace(temporary, directory / "status.yaml")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


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
