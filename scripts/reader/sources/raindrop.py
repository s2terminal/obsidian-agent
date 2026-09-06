"""Raindrop の GET 専用クライアント。状態・要約・出力には依存しない。"""
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode

from reader.models import FetchResult, RaindropCursor, SourceArticle, SourceFetchError, utc_datetime
from reader.sources import raindrop_url
from reader.sources.rss import resolve_title

API_ROOT = 'https://api.raindrop.io/rest/v1/raindrops/'
PAGE_SIZE = 50
NESTED = False
MAX_PAGES = 3  # 1回の走査で取得するページ数の上限（50件×3 = 約150件）。超える新着は取得エラーにして次回へ回す。


class JsonGetTransport(Protocol):
    def get(self, url: str, *, params: dict, headers: dict) -> dict: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # 認証ヘッダーを別のホストへ転送しない。
        return None


class UrllibJsonGetTransport:
    ATTEMPTS = 3        # タイムアウト・5xx・429 の再試行回数上限
    TIMEOUT = 30        # 1リクエストのタイムアウト秒数

    def __init__(self, *, opener=None, sleep=time.sleep):
        self.opener = opener or urllib.request.build_opener(_NoRedirect())
        self.sleep = sleep

    def get(self, url: str, *, params: dict, headers: dict) -> dict:
        if not re.fullmatch(re.escape(API_ROOT) + r'(?:[0-9]+|-1)', url):
            raise SourceFetchError('未対応のRaindrop APIです')
        request_url = url + '?' + urlencode(params)
        for attempt in range(self.ATTEMPTS):
            request = urllib.request.Request(request_url, headers=headers, method='GET')
            try:
                with self.opener.open(request, timeout=self.TIMEOUT) as response:
                    data = json.load(response)
                if not isinstance(data, dict):
                    raise SourceFetchError('Raindropのレスポンス形式が不正です')
                return data
            except urllib.error.HTTPError as error:
                code = error.code
                error.close()
                # 恒常的な 4xx（401/403/404 等）は再試行しない。
                if code != 429 and not 500 <= code < 600:
                    raise SourceFetchError(f'Raindrop APIの取得に失敗しました（HTTP {code}）') from None
            except (urllib.error.URLError, TimeoutError, OSError):
                pass
            except (ValueError, UnicodeError):
                raise SourceFetchError('RaindropのJSONが不正です') from None
            if attempt == self.ATTEMPTS - 1:
                raise SourceFetchError('Raindrop APIの再試行上限を超えました') from None
            self.sleep(2 ** attempt)  # 指数バックオフ: 1秒, 2秒
        raise AssertionError('到達しない分岐')


@dataclass(frozen=True)
class RaindropSourceConfig:
    url: str
    title: str | None = None


def _metadata(item):
    if not isinstance(item, dict) or type(item.get('_id')) is not int or item['_id'] <= 0:
        raise SourceFetchError('Raindropの記事IDが不正です')
    try:
        return str(item['_id']), utc_datetime(item.get('created'))
    except ValueError:
        raise SourceFetchError('Raindropの保存日時が不正です') from None


def _article(item, url, eid, created):
    link = item.get('link')
    if not isinstance(link, str) or not link.strip():
        raise SourceFetchError('Raindropの記事リンクが不正です')
    title = item.get('title')
    title = title.strip() if isinstance(title, str) and title.strip() else link
    excerpt = item.get('excerpt')
    content = excerpt.strip() if isinstance(excerpt, str) else ''
    if content == title or re.fullmatch(r'https?://\S+', content):
        content = ''
    return SourceArticle(eid, url, 'raindrop', title, link, content or None,
                         'excerpt' if content else 'none', None, created)


class RaindropClient:
    def __init__(self, *, token: str, transport: JsonGetTransport):
        if not isinstance(token, str) or not token.strip() or '\n' in token or '\r' in token:
            raise SourceFetchError('Raindropのトークンが未設定または不正です')
        self._token = token.strip()
        self.transport = transport

    def fetch(self, *, source: RaindropSourceConfig, cursor: RaindropCursor | None) -> FetchResult:
        url, collection = raindrop_url(source.url)
        # API公式仕様: /raindrops/{collectionId}, pageは0始まり、最大50件。
        # https://developer.raindrop.io/v1/raindrops/multiple
        # /my/<ID> はReaderが受け付けるアプリURL形式。Web画面を取得せずIDだけを使用する。
        selected = []
        seen = set()
        boundary = cursor.last_fetched if cursor else None
        newest = boundary
        boundary_ids = set(cursor.boundary_ids) if cursor else set()
        for page in range(MAX_PAGES):
            data = self.transport.get(API_ROOT + str(collection),
                params={'sort': '-created', 'perpage': PAGE_SIZE, 'page': page, 'nested': str(NESTED).lower()},
                headers={'Authorization': 'Bearer ' + self._token, 'Accept': 'application/json'})
            if not isinstance(data, dict) or data.get('result') is not True or not isinstance(data.get('items'), list):
                raise SourceFetchError('Raindropの一覧レスポンスが不正です')
            items = data['items']
            older = False
            seen_before = len(seen)
            for item in items:
                eid, created = _metadata(item)
                if boundary is None:
                    boundary = created
                    newest = created
                if created < boundary:
                    older = True
                    continue
                # 初回走査中に境界より新しい保存が挿入されても、次回へ残す。
                if cursor is None and created > boundary:
                    continue
                if eid in seen:
                    continue
                seen.add(eid)
                if newest is None or created > newest:
                    newest, boundary_ids = created, {eid}
                elif created == newest:
                    boundary_ids.add(eid)
                if cursor is None:
                    if not selected:
                        selected.append(_article(item, url, eid, created))
                elif created > cursor.last_fetched or eid not in cursor.boundary_ids:
                    selected.append(_article(item, url, eid, created))
            if older or len(items) < PAGE_SIZE:
                break
            if len(seen) == seen_before:
                raise SourceFetchError("Raindropのページ取得が進みません")
        else:
            # MAX_PAGES 分すべて満杯で走査しきれなかった。取得位置を進めず次回に回す。
            raise SourceFetchError(f"Raindropの新着が多すぎます（{MAX_PAGES * PAGE_SIZE}件超）")
        next_cursor = RaindropCursor(newest, frozenset(boundary_ids)) if newest else None
        return FetchResult(selected, resolve_title({'title': source.title}, 'Raindrop の後で読む'), url, next_cursor)
