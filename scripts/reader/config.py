import os
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).parent
CACHE_DIR = SCRIPT_DIR / ".cache"

Models = Literal["gemini-2.5-flash", "gemini-2.5-pro", "gemini-3-flash-preview"]
DEFAULT_MODEL = "gemini-3-flash-preview"

APP_NAME = "rss_reader"
USER_ID = "default_user"
MAX_ARTICLES = 5  # フィードごとに要約する最大記事数
MAX_ARTICLES_NEW = 1  # last_fetched 未設定（新規追加）フィードに適用する最大記事数

def safe_getenv(key: str) -> str:
    value = os.getenv(key)
    if value is None:
        raise EnvironmentError(f"環境変数 {key} が設定されていません。")
    return value

def get_feed_yaml() -> Path:
    return Path(safe_getenv("FEED_YAML"))


def get_feed_out_dir() -> Path:
    return Path(safe_getenv("OBSIDIAN_ROOT")) / "ai-generated" / "feed"


def get_slack_webhook_url() -> str:
    return safe_getenv("SLACK_WEBHOOK_URL")


def get_timezone() -> ZoneInfo:
    return ZoneInfo(safe_getenv("TIMEZONE"))
