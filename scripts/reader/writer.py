from datetime import datetime, timezone
from pathlib import Path

from reader.config import get_feed_out_dir


def write_news(new_articles: list[dict], feed_out_dir: Path | None = None):
    out_dir = feed_out_dir or get_feed_out_dir()
    # ファイル名はスクリプト実行日
    today = datetime.now(timezone.utc)
    md_path = out_dir / today.strftime("%Y") / today.strftime("%m-%d.md")
    md_path.parent.mkdir(parents=True, exist_ok=True)

    existing = md_path.read_text(encoding="utf-8") if md_path.exists() else ""

    # 記事をフィードごとにグループ化
    by_date: dict[str, dict[tuple[str, str], list[dict]]] = {}
    for a in new_articles:
        date_key = a["published"]
        feed_key = (a.get("feed_title", ""), a.get("feed_link", ""))
        by_date.setdefault(date_key, {}).setdefault(feed_key, []).append(a)

    lines: list[str] = []
    for date_str in sorted(by_date.keys(), reverse=True):
        lines.append(f"## {date_str}\n")
        for (feed_title, feed_link), articles in by_date[date_str].items():
            lines.append(f"### [{feed_title}]({feed_link})\n")
            for a in articles:
                lines.append(f"#### [{a['title']}]({a['link']})\n")
                lines.append(f"{a['summary']}\n")

    if existing:
        md_path.write_text(existing.rstrip("\n") + "\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
    else:
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
