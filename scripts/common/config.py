import os
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

Models = Literal["gemini-2.5-flash", "gemini-2.5-pro", "gemini-3-flash-preview"]
DEFAULT_MODEL = "gemini-3-flash-preview"


def safe_getenv(key: str) -> str:
    value = os.getenv(key)
    if value is None:
        raise EnvironmentError(f"環境変数 {key} が設定されていません。")
    return value


def get_obsidian_root() -> Path:
    return Path(safe_getenv("OBSIDIAN_ROOT"))


def get_ai_generated_dir(subdir: str) -> Path:
    return get_obsidian_root() / "ai-generated" / subdir


def get_slack_webhook_url() -> str:
    return safe_getenv("SLACK_WEBHOOK_URL")


def get_timezone() -> ZoneInfo:
    return ZoneInfo(safe_getenv("TIMEZONE"))
