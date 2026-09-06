"""
Reader & Summarizer

フィードから最新記事を取得し、Google ADK (Gemini) で要約して出力する。
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from contextlib import nullcontext

from reader.sources import rss, markdown, source_type
from reader.models import SourceFetchError
from google.adk.apps import App
from google.adk.runners import InMemoryRunner

from common.obsidian import build_obsidian_open_url
from reader.cache import load_cache, save_cache
from reader.config import APP_NAME, MAX_ARTICLES, MAX_ARTICLES_NEW, get_feed_out_dir, get_obsidian_agent_dir
from reader.feed import feed_importance, load_feeds, parse_last_fetched, save_status
from reader.notifier import notify_slack
from reader.summarizer import summarize, summarizer_agent
from reader.writer import render_news, write_news
from reader.state import reader_lock
from reader.sources.raindrop import UrllibJsonGetTransport
from reader.raindrop_processor import process_raindrop, mark_output_done


async def process_feed(
    runner: InMemoryRunner, feed_info: dict, *, summarize_only: bool = False
) -> tuple[list[dict], list[str]]:
    url = feed_info["url"]
    print(f"フィード取得中: {url}")

    is_markdown = source_type(feed_info) == "markdown"
    try:
        result = (markdown if is_markdown else rss).fetch(feed_info)
    except SourceFetchError as exc:
        # RSS の一時的な取得失敗は既存挙動どおりログのみ（通知しない）。
        # Markdown はフォーマット不正を検知する目的なので従来どおり通知する。
        if is_markdown:
            return [], [str(exc)]
        print(f"  取得失敗: {exc}: {url}")
        return [], []
    entries = result.articles
    feed_title, feed_link = result.source_title, result.source_link

    cache = load_cache(url)
    importance = feed_importance(feed_info)
    articles: list[dict] = []
    summarized_ids: list[str] = []

    # last_fetched を解析して、それより新しい記事のみ処理する
    last_fetched = parse_last_fetched(feed_info)

    # last_fetched が未設定（新規追加）の場合は最新1件のみ処理する
    default_max = MAX_ARTICLES_NEW if last_fetched is None else MAX_ARTICLES
    max_articles = feed_info.get("max_articles", default_max)

    for entry in entries:
        eid = entry.id
        cached_entry = cache.get(eid)

        # 新規記事は last_fetched より古ければスキップ
        if not cached_entry and last_fetched:
            pub_dt = entry.published_at
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
            title = entry.title
            link = entry.link
            content = entry.content or ""
            published = entry.display_date

        try:
            summary = await summarize(runner, str(title), content, importance=importance)
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

    if not summarize_only:
        save_cache(url, cache)
    print(f"  新規要約: {len(summarized_ids)}件")
    return articles, []


async def _main(*, summarize_only: bool = False):
    feeds_data = load_feeds()
    app = App(name=APP_NAME, root_agent=summarizer_agent)
    runner = InMemoryRunner(app=app)

    all_articles: list[dict] = []
    all_errors: list[str] = []
    updated_feeds: list[dict] = []
    active_feeds = [f for f in feeds_data["feeds"] if f.get("active") is not False]
    transport = UrllibJsonGetTransport()
    for feed_info in active_feeds:
        if source_type(feed_info) == "raindrop":
            articles, errors = await process_raindrop(runner, feed_info, summarize=summarize,
                transport=transport, summarize_only=summarize_only)
        else:
            articles, errors = await process_feed(runner, feed_info, summarize_only=summarize_only)
            if articles:
                updated_feeds.append(feed_info)
        all_articles.extend(articles)
        all_errors.extend(errors)

    pending_count = sum(
        item.get("status") != "done"
        for feed in active_feeds
        for item in feed.get("_state", {}).get("items", {}).values()
    )
    pending_count -= sum("_raindrop_id" in article for article in all_articles)
    pending_section = f"\nRaindrop 未処理: {pending_count}件" if any(source_type(f) == "raindrop" for f in active_feeds) else ""
    error_section = ""
    if all_errors:
        error_lines = "\n".join(f"• {e}" for e in all_errors)
        error_section = f"\n:warning: 取得・処理エラー:\n{error_lines}"

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
        if updated_feeds:
            save_status({"feeds": updated_feeds})

        rel = Path("ai-generated") / "feed" / output_md_full_path.resolve().relative_to(
            get_feed_out_dir().resolve()
        )
        mark_output_done(all_articles)
        obsidian_url = build_obsidian_open_url(rel)
        msg = (
            f"ai-generated/feed/ に {len(all_articles)}件の記事を追加しました\n"
            f"{obsidian_url}"
        )
        print(f"\n{msg}")
        if error_section:
            print(error_section)
        notify_slack(f":newspaper: Reader 完了: {msg}{pending_section}{error_section}")
    else:
        print("\n新規記事はありません")
        if error_section:
            print(error_section)
        if not summarize_only:
            notify_slack(f":newspaper: Reader 完了: 新規記事はありません{pending_section}{error_section}")


async def main(*, summarize_only: bool = False):
    lock = nullcontext() if summarize_only else reader_lock(get_obsidian_agent_dir())
    with lock:
        await _main(summarize_only=summarize_only)


def run(*, summarize_only: bool = False):
    asyncio.run(main(summarize_only=summarize_only))
