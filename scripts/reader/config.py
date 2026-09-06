from pathlib import Path

from common.config import (
    DEFAULT_MODEL,
    Models,
    get_ai_generated_dir,
    get_obsidian_root,
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
    "get_obsidian_agent_dir",
    "get_feed_out_dir",
    "get_raindrop_access_token",
]

SCRIPT_DIR = Path(__file__).parent
CACHE_DIR = SCRIPT_DIR / ".cache"

APP_NAME = "rss_reader"
USER_ID = "default_user"
MAX_ARTICLES = 5  # フィードごとに要約する最大記事数
MAX_ARTICLES_NEW = 1  # last_fetched 未設定（新規追加）フィードに適用する最大記事数


def get_obsidian_agent_dir() -> Path:
    relative_path = Path(safe_getenv("OBSIDIAN_AGENT_DIR"))
    if relative_path.is_absolute():
        raise ValueError("OBSIDIAN_AGENT_DIRにはOBSIDIAN_ROOTからの相対パスを指定してください")
    path = get_obsidian_root() / relative_path
    if path.is_file():
        raise ValueError("OBSIDIAN_AGENT_DIRにはディレクトリを指定してください")
    return path


def get_feed_out_dir() -> Path:
    return get_ai_generated_dir("feed")


def get_raindrop_access_token() -> str:
    token = safe_getenv('RAINDROP_ACCESS_TOKEN').strip()
    if not token or '\r' in token or '\n' in token:
        raise ValueError('RAINDROP_ACCESS_TOKENが未設定または不正です')
    return token
