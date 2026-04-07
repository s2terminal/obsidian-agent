from datetime import datetime
from pathlib import Path

from .config import get_feed_out_dir, get_timezone


def render_news(new_articles: list[dict]) -> str:
    # 記事をフィードごとにグループ化
    by_date: dict[str, dict[tuple[str, str], list[dict]]] = {}
    for article in new_articles:
        date_key = article["published"]
        feed_key = (article.get("feed_title", ""), article.get("feed_link", ""))
        by_date.setdefault(date_key, {}).setdefault(feed_key, []).append(article)

    lines: list[str] = []
    for date_str in sorted(by_date.keys(), reverse=True):
        lines.append(f"## {date_str}\n")
        for (feed_title, feed_link), articles in by_date[date_str].items():
            lines.append(f"### [{feed_title}]({feed_link})\n")
            for article in articles:
                lines.append(f"#### [{article['title']}]({article['link']})\n")
                lines.append(f"{article['summary']}\n")

    return "\n".join(lines).rstrip("\n") + "\n" if lines else ""


def write_news(new_articles: list[dict], feed_out_dir: Path | None = None):
    out_dir = feed_out_dir or get_feed_out_dir()
    # ファイル名はスクリプト実行日（設定タイムゾーン準拠）
    today = datetime.now(get_timezone())
    md_path = out_dir / today.strftime("%Y") / today.strftime("%m-%d.md")
    md_path.parent.mkdir(parents=True, exist_ok=True)

    existing = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    rendered = render_news(new_articles)

    if existing:
        md_path.write_text(existing.rstrip("\n") + "\n\n" + rendered, encoding="utf-8")
    else:
        md_path.write_text(rendered, encoding="utf-8")

    return md_path
