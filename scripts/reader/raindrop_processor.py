"""保存した Raindrop 記事の要約と出力待ち状態を管理する。"""
from copy import deepcopy
from datetime import datetime, timezone

from reader.config import MAX_ARTICLES, MAX_ARTICLES_NEW, get_obsidian_agent_dir, get_raindrop_access_token, get_timezone
from reader.feed import feed_importance
from reader.models import SourceFetchError, utc_datetime
from reader.sources.raindrop import RaindropClient, RaindropSourceConfig
from reader.sources.rss import resolve_title
from reader.state import cursor_from_state, load_state, save_state

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _time(value: object) -> datetime:
    """保存済みの日時文字列を UTC datetime に。欠損・不正はエポック扱い（末尾ソート・処理は継続）。"""
    try:
        return utc_datetime(value)
    except ValueError:
        return _EPOCH


def _has_excerpt(item: dict) -> bool:
    content = item.get("content")
    return isinstance(content, str) and bool(content.strip())


def _persist(url, state):
    directory = get_obsidian_agent_dir()
    data = load_state(directory)
    data["raindrop"][url] = state
    save_state(directory, data)


async def process_raindrop(runner, feed, *, summarize, transport, summarize_only=False):
    url = feed["url"]
    state = deepcopy(feed.get("_state") or {"items": {}, "boundary_ids": []})
    cursor = cursor_from_state(state)
    errors = []
    try:
        token = get_raindrop_access_token()
    except (OSError, ValueError):
        token = None
        errors.append(f"Raindropのトークンが未設定または不正です: {url}")

    # stateに詰め込む
    if token is not None:
        try:
            result = RaindropClient(token=token, transport=transport).fetch(
                source=RaindropSourceConfig(url, feed.get("title")), cursor=cursor)
        except SourceFetchError as exc:
            errors.append(f"{exc}: {url}")
        else:
            for article in result.articles:
                state["items"].setdefault(article.id, {
                    "title": article.title, "link": article.link,
                    "content": article.content,
                    "saved_at": article.saved_at.isoformat(),
                    "status": "pending", "summary": None,
                })
            if result.next_cursor:
                state["last_fetched"] = result.next_cursor.last_fetched.isoformat()
                state["boundary_ids"] = sorted(result.next_cursor.boundary_ids)
            if not summarize_only:
                _persist(url, state)

    # APIに残っているかに関係なく、保存済みの記事を再試行する。
    candidates = [(eid, item) for eid, item in state["items"].items()
                  if isinstance(item, dict) and item.get("status") != "done"]
    candidates.sort(key=lambda pair: (_time(pair[1].get("last_attempted_at")), _time(pair[1].get("saved_at")), pair[0]))
    limit = MAX_ARTICLES_NEW if cursor is None else feed.get("max_articles", MAX_ARTICLES)
    articles = []
    for eid, item in candidates[:limit]:
        item["last_attempted_at"] = datetime.now(timezone.utc).isoformat()
        title = item.get("title") or item.get("link") or ""
        if item.get("status", "pending") == "pending":
            try:
                if _has_excerpt(item):
                    item["summary"] = await summarize(runner, title, item["content"],
                        importance=feed_importance(feed), content_kind="excerpt")
                    if not item["summary"] or not item["summary"].strip():
                        raise ValueError("要約が空です")
                item["status"] = "ready"
            except Exception:
                # LLMの例外には入力等を含む場合があるため、生の例外は通知しない。
                errors.append(f"Raindropの要約に失敗しました（記事ID: {eid}）: {url}")
                if not summarize_only:
                    _persist(url, state)
                continue
        if not summarize_only:
            _persist(url, state)
        articles.append({
            "title": title, "link": item.get("link", ""), "summary": item.get("summary"),
            "published": _time(item.get("saved_at")).astimezone(get_timezone()).strftime("%Y/%m/%d"),
            "feed_title": resolve_title(feed, "Raindrop の後で読む") + "（保存日）", "feed_link": url,
            "content_kind": "excerpt" if _has_excerpt(item) else "none", "_raindrop_id": eid, "_source_url": url,
        })
    feed["_state"] = state
    return articles, errors


def mark_output_done(articles: list[dict]) -> None:
    raindrops = [a for a in articles if "_raindrop_id" in a]
    if not raindrops:
        return
    directory = get_obsidian_agent_dir()
    data = load_state(directory)
    for article in raindrops:
        items = data["raindrop"].get(article["_source_url"], {}).get("items", {})
        if article["_raindrop_id"] in items:
            items[article["_raindrop_id"]]["status"] = "done"
    save_state(directory, data)
