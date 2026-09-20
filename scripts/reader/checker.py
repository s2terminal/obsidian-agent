"""フィード設定の確認と、取得・要約のドライラン。

いずれのモードでも status.yaml・キャッシュ・要約ファイルには書き込まない。
"""
from reader.cache import load_cache
from reader.config import MAX_ARTICLES, MAX_ARTICLES_NEW, get_raindrop_access_token
from reader.feed import feed_id, load_feeds, parse_last_fetched
from reader.models import FetchResult, SourceFetchError
from reader.sources import markdown, rss, source_type, raindrop_url
from reader.sources.raindrop import RaindropClient, RaindropSourceConfig, UrllibJsonGetTransport
from reader.state import cursor_from_state


def _pending_count(feed: dict) -> int:
    return sum(item.get("status") != "done" for item in (feed.get("_state") or {}).get("items", {}).values())


def _fetch_source(feed: dict) -> FetchResult:
    """ソース種別ごとに実際の取得を行う。状態の保存も要約も行わない。"""
    if source_type(feed) == "raindrop":
        client = RaindropClient(token=get_raindrop_access_token(), transport=UrllibJsonGetTransport())
        return client.fetch(
            source=RaindropSourceConfig(feed["url"], feed.get("title")),
            cursor=cursor_from_state(feed.get("_state") or {}),
        )
    return (markdown if source_type(feed) == "markdown" else rss).fetch(feed)


def _print_fetch(feed: dict) -> None:
    """フィードを取得し、要約対象になる件数の目安を表示する。"""
    try:
        result = _fetch_source(feed)
    except SourceFetchError as exc:
        print(f"    fetch        : 失敗 ({exc})")
        return
    except Exception as exc:
        # 取得エラー以外（トークン未設定など）は秘密情報が混ざり得るため、例外の型だけを示す。
        print(f"    fetch        : 失敗 ({type(exc).__name__})")
        return

    last_fetched = parse_last_fetched(feed)
    if source_type(feed) == "raindrop":
        # Raindrop API は取得位置より新しい記事だけを返す。再試行対象は保存済みの未完了記事。
        new_count = len(result.articles)
        retry_count = _pending_count(feed)
    else:
        new_count = sum(
            last_fetched is None or article.published_at is None or article.published_at > last_fetched
            for article in result.articles
        )
        retry_count = len(load_cache(feed["url"]))
    limit = feed.get("max_articles", MAX_ARTICLES_NEW if last_fetched is None else MAX_ARTICLES)

    print("    fetch        : 成功")
    print(f"    source_title : {result.source_title}")
    print(f"    entries      : {len(result.articles)}件")
    print(f"    new_entries  : {new_count}件")
    print(f"    retry        : {retry_count}件")
    print(f"    summarize    : 最大{min(new_count + retry_count, limit)}件（上限 {limit}件・目安）")


def check(*, fetch: bool = False, summarize: bool = False) -> None:
    """ソース設定と取得位置・未処理件数を表示する。

    fetch: 実際にフィードを取得して、取得件数と要約対象の目安を表示する。
    summarize: 取得に加えて要約まで行い、標準出力へ流す（ファイルや状態は更新しない）。
    """
    feeds_data = load_feeds()
    feeds = feeds_data.get("feeds", [])
    print(f"フィード数: {len(feeds)}")
    for i, feed in enumerate(feeds, 1):
        fid = feed_id(feed) or "(ID未設定)"
        active = feed.get("active", True)
        url = feed.get("url", "(url未設定)")
        title = feed.get("title") or "(タイトル未設定)"
        last_fetched = feed.get("last_fetched") or "(未取得)"
        max_articles = feed.get("max_articles", "(デフォルト)")
        importance = feed.get("importance", "(デフォルト)")
        status = "[active]" if active else " [無効]"
        print(f"\n[{i}] {fid} {status}")
        print(f"    type         : {source_type(feed)}")
        if source_type(feed) == "raindrop":
            print(f"    collection   : {raindrop_url(url)[1]}")
            print(f"    pending      : {_pending_count(feed)}")
        print(f"    title        : {title}")
        print(f"    url          : {url}")
        print(f"    last_fetched : {last_fetched}")
        print(f"    max_articles : {max_articles}")
        print(f"    importance   : {importance}")
        # 要約モードでは取得と要約をまとめて行うため、ここでは取得しない（二重取得の回避）。
        if fetch and not summarize and active:
            _print_fetch(feed)

    if summarize:
        from reader.main import run as run_reader_main
        print("\n要約ドライラン:")
        run_reader_main(summarize_only=True)
