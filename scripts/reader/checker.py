from reader.feed import feed_id, load_feeds


def check():
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
        status = "[active]" if active else " [無効]"
        print(f"\n[{i}] {fid} {status}")
        print(f"    title        : {title}")
        print(f"    url          : {url}")
        print(f"    last_fetched : {last_fetched}")
        print(f"    max_articles : {max_articles}")
