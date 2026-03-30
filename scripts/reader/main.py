"""
RSS Reader & Summarizer

フィードから最新記事を取得し、Google ADK (Gemini) で要約してnews.mdに出力する。

usage:
    mise x -- uv run ./scripts/reader/main.py
"""

import asyncio
from datetime import datetime, timezone

import feedparser
from google.adk.runners import InMemoryRunner

from reader.cache import load_cache, save_cache
from reader.config import APP_NAME, MAX_ARTICLES
from reader.feed import load_feeds, save_feeds
from reader.notifier import notify_slack
from reader.parser import entry_content, entry_id, entry_published_date
from reader.summarizer import summarize, summarizer_agent
from reader.writer import write_news


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

        # フィードのlast_fetchedを更新して保存
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
