"""Markdown形式の更新履歴をフィードエントリとして返すパーサー。

Google Cloud リリースノートなど、## Month DD, YYYY 形式の日付H2見出しを持つ
Markdown ファイルを feedparser エントリ互換の dict リストとして返す。
"""

import hashlib
import urllib.request
from datetime import datetime, timezone
from time import struct_time


def is_markdown_feed(feed_info: dict) -> bool:
    """フィード設定がMarkdown形式かどうかを返す。

    URLが .md または .md.txt で終わる場合、または type: markdown が設定されている場合に True。
    """
    if feed_info.get("type") == "markdown":
        return True
    url = feed_info.get("url", "")
    return url.endswith(".md") or url.endswith(".md.txt")


def _parse_date(heading: str) -> struct_time | None:
    date_str = heading.lstrip("#").strip()
    try:
        return datetime.strptime(date_str, "%B %d, %Y").replace(tzinfo=timezone.utc).timetuple()
    except ValueError:
        return None


def _section_id(url: str, heading: str) -> str:
    return f"{url}#{hashlib.sha256(heading.encode()).hexdigest()[:16]}"


def parse_md_feed(url: str, text: str) -> list[dict]:
    """Markdown テキストを日付セクション単位のエントリリストに変換する。

    ## Month DD, YYYY 形式のH2見出しで分割し、各セクションを1エントリとして返す。
    日付形式でないH2や内容が空のセクションはスキップする。
    """
    entries: list[dict] = []
    lines = text.splitlines()

    current_heading: str | None = None
    current_struct: struct_time | None = None
    current_lines: list[str] = []

    def _flush() -> None:
        if current_heading is None or current_struct is None:
            return
        content = "\n".join(current_lines).strip()
        if not content:
            return
        entries.append({
            "id": _section_id(url, current_heading),
            "link": url,
            "title": current_heading[2:].strip(),
            "summary": content,
            "published_parsed": current_struct,
        })

    for line in lines:
        if line.startswith("## "):
            _flush()
            current_heading = line
            current_struct = _parse_date(line)
            current_lines = []
        elif current_heading is not None:
            current_lines.append(line)

    _flush()
    return entries


def fetch_md_feed(url: str) -> list[dict]:
    """URL から Markdown ファイルを取得し、エントリリストを返す。"""
    req = urllib.request.Request(url, headers={"User-Agent": "obsidian-agent/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode("utf-8")
    return parse_md_feed(url, text)
