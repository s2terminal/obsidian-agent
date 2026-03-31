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

from .cache import load_cache, save_cache
from .config import APP_NAME, MAX_ARTICLES, MAX_ARTICLES_NEW
from .feed import load_feeds, parse_last_fetched, save_feeds
from .notifier import notify_slack
from .parser import entry_content, entry_id, entry_published_date, entry_published_datetime
from .summarizer import summarize, summarizer_agent
from .writer import write_news


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

    # last_fetched を解析して、それより新しい記事のみ処理する
    last_fetched = parse_last_fetched(feed_info)

    # last_fetched が未設定（新規追加）の場合は最新1件のみ処理する
    default_max = MAX_ARTICLES_NEW if last_fetched is None else MAX_ARTICLES
    max_articles = feed_info.get("max_articles", default_max)

    for entry in feed.entries:
        eid = entry_id(entry)
        cached_entry = cache.get(eid)

        # 新規記事は last_fetched より古ければスキップ
        if not cached_entry and last_fetched:
            pub_dt = entry_published_datetime(entry)
            if pub_dt and pub_dt <= last_fetched:
                continue

        # 上限に達したら、残りの未処理記事をスキップ
        if len(summarized_ids) >= max_articles:
            continue

        # キャッシュにある → リトライ対象（コンテンツをキャッシュから復元）
        if cached_entry:
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
            # fetch済み・要約失敗 → キャッシュに保存してリトライ対象にする
            cache[eid] = {
                "title": title, "link": link,
                "content": content, "published": published,
            }
            continue

        # 要約成功 → キャッシュから削除
        cache.pop(eid, None)

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
