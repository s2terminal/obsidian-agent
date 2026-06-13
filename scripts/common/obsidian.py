import re
from pathlib import Path
from urllib.parse import quote

WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def make_safe_slug(value: str, max_length: int = 60) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', ' ', value)
    cleaned = re.sub(r'\s+', '_', cleaned.strip())
    cleaned = cleaned.strip(' ._')
    cleaned = cleaned[:max_length].rstrip(' ._')
    if not cleaned:
        return "research"
    if cleaned.upper() in WINDOWS_RESERVED_NAMES:
        return f"research_{cleaned.lower()}"
    return cleaned


def build_obsidian_open_url(vault_relative_path: Path, *, vault: str = "RemoteVault") -> str:
    """vault ルートからの相対パスを Obsidian の open URL に変換する。"""
    return (
        f"obsidian://open?vault={quote(vault, safe='')}&file="
        f"{quote(vault_relative_path.as_posix(), safe='/')}"
    )
