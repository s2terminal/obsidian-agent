"""
RSS Reader & Summarizer

フィードから最新記事を取得し、Google ADK (Gemini) で要約して出力する。
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import feedparser
from google.adk.apps import App
from google.adk.runners import InMemoryRunner

from common.obsidian import build_obsidian_open_url
from reader.cache import load_cache, save_cache
from reader.config import APP_NAME, MAX_ARTICLES, MAX_ARTICLES_NEW, get_feed_out_dir
from reader.feed import load_feeds, parse_last_fetched, save_feeds
from reader.md_feed_parser import fetch_md_feed, is_markdown_feed
from reader.notifier import notify_slack
from reader.parser import entry_content, entry_id, entry_published_date, entry_published_datetime
from reader.summarizer import summarize, summarizer_agent
from reader.writer import render_news, write_news


def _resolve_feed_title(feed_info: dict, fallback_title: str) -> str:
    configured_title = feed_info.get("title")
    if isinstance(configured_title, str):
        configured_title = configured_title.strip()
    if configured_title:
        return str(configured_title)
    return fallback_title


async def process_feed(
    runner: InMemoryRunner, feed_info: dict
) -> tuple[list[dict], list[str]]:
    url = feed_info["url"]
    print(f"フィード取得中: {url}")

    if is_markdown_feed(feed_info):
        try:
            entries = fetch_md_feed(url)
        except Exception as e:
            msg = f"Markdownフィードの取得に失敗: {e} ({url})"
            print(f"  エラー: {msg}")
            return [], [msg]
        if not entries:
            msg = f"日付セクションが見つかりません（フォーマット不正の可能性）: {url}"
            print(f"  エラー: {msg}")
            return [], [msg]
        feed_title = _resolve_feed_title(feed_info, url)
        feed_link = url
    else:
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            print("  エラー: フィードの取得に失敗")
            return [], []
        entries = feed.entries
        feed_title = _resolve_feed_title(feed_info, getattr(feed.feed, "title", url) or url)
        feed_link = getattr(feed.feed, "link", url) or url

    cache = load_cache(url)
    articles: list[dict] = []
    summarized_ids: list[str] = []

    # last_fetched を解析して、それより新しい記事のみ処理する
    last_fetched = parse_last_fetched(feed_info)

    # last_fetched が未設定（新規追加）の場合は最新1件のみ処理する
    default_max = MAX_ARTICLES_NEW if last_fetched is None else MAX_ARTICLES
    max_articles = feed_info.get("max_articles", default_max)

    for entry in entries:
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

        articles.append({
            "title": title, "link": link, "summary": summary, "published": published,
            "feed_title": feed_title, "feed_link": feed_link,
        })
        summarized_ids.append(eid)

    save_cache(url, cache)
    print(f"  新規要約: {len(summarized_ids)}件")
    return articles, []


async def main(*, summarize_only: bool = False):
    feeds_data = load_feeds()
    app = App(name=APP_NAME, root_agent=summarizer_agent)
    runner = InMemoryRunner(app=app)

    all_articles: list[dict] = []
    all_errors: list[str] = []
    updated_feeds: list[dict] = []
    for feed_info in feeds_data["feeds"]:
        if feed_info.get("active") is False:
            continue
        articles, errors = await process_feed(runner, feed_info)
        if articles:
            updated_feeds.append(feed_info)
        all_articles.extend(articles)
        all_errors.extend(errors)

    error_section = ""
    if all_errors:
        error_lines = "\n".join(f"• {e}" for e in all_errors)
        error_section = f"\n:warning: フォーマットエラー:\n{error_lines}"

    if all_articles:
        if summarize_only:
            print(render_news(all_articles), end="")
            if error_section:
                print(f"\n{error_section.strip()}")
            print("\n要約のみモード: last_fetched は更新せず、要約ファイルも保存しません")
            return

        output_md_full_path = write_news(all_articles)

        # フィードのlast_fetchedを更新して保存
        now = datetime.now(timezone.utc).isoformat()
        for feed_info in updated_feeds:
            feed_info["last_fetched"] = now
        save_feeds(feeds_data)

        rel = Path("ai-generated") / "feed" / output_md_full_path.resolve().relative_to(
            get_feed_out_dir().resolve()
        )
        obsidian_url = build_obsidian_open_url(rel)
        msg = (
            f"ai-generated/feed/ に {len(all_articles)}件の記事を追加しました\n"
            f"{obsidian_url}"
        )
        print(f"\n{msg}")
        if error_section:
            print(error_section)
        notify_slack(f":newspaper: RSS Reader 完了: {msg}{error_section}")
    else:
        print("\n新規記事はありません")
        if error_section:
            print(error_section)
        if not summarize_only:
            notify_slack(f":newspaper: RSS Reader 完了: 新規記事はありません{error_section}")


def run(*, summarize_only: bool = False):
    asyncio.run(main(summarize_only=summarize_only))
