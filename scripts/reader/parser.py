"""feedparser エントリからメタデータを抽出するユーティリティ。

feedparser が返す個々の記事エントリ (dict-like) から、
ID・本文・投稿日など後続処理に必要な情報を統一的に取り出す。
"""

import hashlib
from datetime import datetime, timezone
from time import mktime, struct_time


def entry_id(entry) -> str:
    """記事の一意識別子を返す。

    feedparser のエントリは id / link / title のいずれかを持つ前提で、
    優先順位は id > link > タイトルの SHA-256 ハッシュ。
    キャッシュのキーとして使う。
    """
    return (
        entry.get("id")
        or entry.get("link")
        or hashlib.sha256(entry.get("title", "").encode()).hexdigest()
    )


def entry_content(entry) -> str:
    """記事の本文テキストを返す。

    feedparser は形式によって本文の格納場所が異なるため、
    content[0].value > summary > description の順でフォールバックする。
    """
    if hasattr(entry, "content") and entry.content:
        return entry.content[0].get("value", "")
    return entry.get("summary", entry.get("description", ""))


def entry_published_datetime(entry) -> datetime | None:
    """記事の投稿日時を datetime オブジェクトで返す。

    published_parsed > updated_parsed の順で参照し、
    いずれも無い場合は None を返す。
    feedparser の parsed 値は UTC の struct_time であるため、
    そのまま UTC の datetime に変換する。
    """
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if isinstance(t, struct_time):
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def entry_published_date(entry) -> str:
    """記事の投稿日を YYYY/MM/DD 形式の文字列で返す。

    published_parsed > updated_parsed の順で参照し、
    いずれも無い場合はスクリプト実行日を返す。
    mktime でローカル時刻の epoch に変換してから UTC に戻しているため、
    タイムゾーンによって±1日のずれが生じ得る点に注意。
    """
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if isinstance(t, struct_time):
            dt = datetime.fromtimestamp(mktime(t), tz=timezone.utc)
            return dt.strftime("%Y/%m/%d")
    return datetime.now(timezone.utc).strftime("%Y/%m/%d （スクリプト実行日）")
