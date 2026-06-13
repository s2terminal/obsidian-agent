from pathlib import Path

from common.config import (
    DEFAULT_MODEL,
    Models,
    get_ai_generated_dir,
    get_slack_webhook_url,
    get_timezone,
    safe_getenv,
)

__all__ = [
    "DEFAULT_MODEL",
    "Models",
    "get_slack_webhook_url",
    "get_timezone",
    "safe_getenv",
    "SCRIPT_DIR",
    "CACHE_DIR",
    "APP_NAME",
    "USER_ID",
    "MAX_ARTICLES",
    "MAX_ARTICLES_NEW",
    "get_feed_md",
    "get_feed_out_dir",
]

SCRIPT_DIR = Path(__file__).parent
CACHE_DIR = SCRIPT_DIR / ".cache"

APP_NAME = "rss_reader"
USER_ID = "default_user"
MAX_ARTICLES = 5  # フィードごとに要約する最大記事数
MAX_ARTICLES_NEW = 1  # last_fetched 未設定（新規追加）フィードに適用する最大記事数


def get_feed_md() -> Path:
    return Path(safe_getenv("FEED_MD"))


def get_feed_out_dir() -> Path:
    return get_ai_generated_dir("feed")
