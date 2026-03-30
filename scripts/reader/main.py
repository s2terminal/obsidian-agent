"""
RSS Reader & Summarizer

フィードから最新記事を取得し、Google ADK (Gemini) で要約してnews.mdに出力する。

usage:
    mise x -- uv run ./scripts/reader/main.py
"""

import asyncio
import hashlib
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import yaml
import os
import feedparser
from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types

SCRIPT_DIR = Path(__file__).parent
FEED_YAML = Path(os.getenv("FEED_YAML"))
FEED_OUT_DIR = Path(os.getenv("OBSIDIAN_ROOT")) / "ai-generated" / "feed"
CACHE_DIR = SCRIPT_DIR / ".cache"

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

Models = Literal["gemini-2.5-flash", "gemini-2.5-pro", "gemini-3-flash-preview"]
DEFAULT_MODEL = "gemini-3-flash-preview"

APP_NAME = "rss_reader"
USER_ID = "default_user"
MAX_ARTICLES = 5  # フィードごとに要約する最大記事数

summarizer_agent = Agent(
    name="summarizer",
    model=DEFAULT_MODEL,
    instruction=(
        "あなたは記事要約アシスタントです。"
        "与えられた記事を日本語で3〜5個の箇条書きで要約してください。"
        "各項目は「- 」で始め、簡潔に1〜2文でまとめてください。"
        "箇条書きのみを出力し、それ以外の前置きや説明は不要です。"
        "すべての内容は日本語で出力してください。"
        "5W1Hをできるだけ明確にしてください。誤「新機能をリリース」→正「x月x日、GitHubが新機能をリリース」"
    ),
)


def notify_slack(message: str):
    """Slack Webhook で通知を送信する。"""
    payload = json.dumps({"text": message})
    data = urllib.parse.urlencode({"payload": payload}).encode("utf-8")
    req = urllib.request.Request(SLACK_WEBHOOK_URL, data=data, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"Slack通知送信完了 (status={resp.status})")
    except Exception as e:
        print(f"Slack通知送信失敗: {e}")


def load_feeds() -> dict:
    with open(FEED_YAML, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_feeds(data: dict):
    with open(FEED_YAML, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def _cache_path(feed_url: str) -> Path:
    return CACHE_DIR / (hashlib.sha256(feed_url.encode()).hexdigest() + ".json")


def load_cache(feed_url: str) -> dict[str, dict]:
    """キャッシュを読み込む。各エントリは {title, link, content, summary, status} を持つ。"""
    p = _cache_path(feed_url)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 旧形式(リスト)からの移行
            if isinstance(data, list):
                return {eid: {"status": "done"} for eid in data}
            return data
    return {}


def save_cache(feed_url: str, cache: dict[str, dict]):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(_cache_path(feed_url), "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)


def entry_id(entry) -> str:
    return (
        entry.get("id")
        or entry.get("link")
        or hashlib.sha256(entry.get("title", "").encode()).hexdigest()
    )


def entry_content(entry) -> str:
    if hasattr(entry, "content") and entry.content:
        return entry.content[0].get("value", "")
    return entry.get("summary", entry.get("description", ""))


def entry_published_date(entry) -> str:
    """記事の投稿日を YYYY/MM/DD 形式で返す。取得できなければ実行日を返す。"""
    from time import mktime, struct_time
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if isinstance(t, struct_time):
            dt = datetime.fromtimestamp(mktime(t), tz=timezone.utc)
            return dt.strftime("%Y/%m/%d")
    return datetime.now(timezone.utc).strftime("%Y/%m/%d （スクリプト実行日）")


async def summarize(runner: InMemoryRunner, title: str, content: str) -> str:
    message = (
        f"以下の記事を日本語で要約してください。\n\n"
        f"タイトル: {title}\n\n"
        f"内容:\n{content[:8000]}"
    )
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID
    )
    responses: list[str] = []
    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session.id,
        new_message=types.Content(
            role="user", parts=[types.Part(text=message)]
        ),
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    responses.append(part.text)
    return "".join(responses).strip()


async def process_feed(
    runner: InMemoryRunner, feed_info: dict
) -> list[dict]:
    url = feed_info["url"]
    print(f"フィード取得中: {url}")

    feed = feedparser.parse(url)
    if feed.bozo and not feed.entries:
        print("  エラー: フィードの取得に失敗")
        return []

    cache = load_cache(url)
    articles: list[dict] = []
    summarized_ids: list[str] = []
    max_articles = feed_info.get("max_articles", MAX_ARTICLES)

    for entry in feed.entries:
        eid = entry_id(entry)
        cached_entry = cache.get(eid)

        # 要約済み・スキップ済みならスキップ
        if cached_entry and cached_entry.get("status") in ("done", "skipped"):
            continue

        # 上限に達したら、残りの未処理記事をスキップ済みとしてマーク
        if len(summarized_ids) >= max_articles:
            if not cached_entry:
                cache[eid] = {"status": "skipped"}
            continue

        # pending(fetch済み・要約未完了)ならキャッシュからコンテンツを復元
        if cached_entry and cached_entry.get("status") == "pending":
            title = cached_entry["title"]
            link = cached_entry["link"]
            content = cached_entry["content"]
            published = cached_entry.get("published", datetime.now(timezone.utc).strftime("%Y/%m/%d"))
            print(f"  要約リトライ タイトル: {title}")
        else:
            title = entry.get("title", "No Title")
            link = entry.get("link", "")
            content = entry_content(entry)
            published = entry_published_date(entry)

        try:
            summary = await summarize(runner, str(title), content)
        except Exception as e:
            print(f"  要約失敗 タイトル: {title} エラー: {e}")
            # fetch済み・要約失敗 → pendingとしてキャッシュ
            cache[eid] = {
                "title": title, "link": link,
                "content": content, "published": published,
                "status": "pending",
            }
            continue

        # 要約成功 → doneとしてキャッシュ
        cache[eid] = {"status": "done"}

        feed_title = getattr(feed.feed, "title", url) or url
        feed_link = getattr(feed.feed, "link", url) or url

        articles.append({
            "title": title, "link": link, "summary": summary, "published": published,
            "feed_title": feed_title, "feed_link": feed_link,
        })
        summarized_ids.append(eid)

    save_cache(url, cache)
    print(f"  新規要約: {len(summarized_ids)}件")
    return articles


def write_news(new_articles: list[dict]):
    # ファイル名はスクリプト実行日
    today = datetime.now(timezone.utc)
    md_path = FEED_OUT_DIR / today.strftime("%Y") / today.strftime("%m-%d.md")
    md_path.parent.mkdir(parents=True, exist_ok=True)

    existing = md_path.read_text(encoding="utf-8") if md_path.exists() else ""

    # 記事をフィードごとにグループ化
    by_date: dict[str, dict[str, list[dict]]] = {}
    for a in new_articles:
        date_key = a["published"]
        feed_key = f"{a.get('feed_title', '')}|{a.get('feed_link', '')}"
        by_date.setdefault(date_key, {}).setdefault(feed_key, []).append(a)

    lines: list[str] = []
    for date_str in sorted(by_date.keys(), reverse=True):
        if f"## {date_str}" not in existing:
            lines.append(f"## {date_str}\n")
        for feed_key, articles in by_date[date_str].items():
            feed_title, feed_link = feed_key.split("|", 1)
            lines.append(f"### [{feed_title}]({feed_link})\n")
            for a in articles:
                lines.append(f"#### [{a['title']}]({a['link']})\n")
                lines.append(f"{a['summary']}\n")

    if existing:
        md_path.write_text(existing.rstrip("\n") + "\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
    else:
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main():
    feeds_data = load_feeds()
    runner = InMemoryRunner(agent=summarizer_agent, app_name=APP_NAME)

    all_articles: list[dict] = []
    updated_feeds: list[dict] = []
    for feed_info in feeds_data["feeds"]:
        articles = await process_feed(runner, feed_info)
        if articles:
            updated_feeds.append(feed_info)
        all_articles.extend(articles)

    if all_articles:
        write_news(all_articles)
        now = datetime.now(timezone.utc).isoformat()
        for feed_info in updated_feeds:
            feed_info["last_fetched"] = now
        save_feeds(feeds_data)
        msg = f"ai-generated/feed/ に {len(all_articles)}件の記事を追加しました"
        print(f"\n{msg}")
        notify_slack(f":newspaper: RSS Reader 完了: {msg}")
    else:
        print("\n新規記事はありません")
        notify_slack(":newspaper: RSS Reader 完了: 新規記事はありません")


if __name__ == "__main__":
    asyncio.run(main())
