import io
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest

from reader.models import RaindropCursor, SourceFetchError
from reader.sources.raindrop import RaindropClient, RaindropSourceConfig, UrllibJsonGetTransport, API_ROOT, _NoRedirect

URL = 'https://app.raindrop.io/my/12'
BASE = datetime(2026, 9, 1, tzinfo=timezone.utc)


def item(eid, days=0, excerpt='抜粋の本文'):
    return {'_id': eid, 'created': (BASE + timedelta(days=days)).isoformat(),
            'title': f'記事{eid}', 'link': f'https://example.com/{eid}', 'excerpt': excerpt}


def fetch(pages, cursor=None):
    transport = Mock()
    transport.get.side_effect = [{'result': True, 'items': p} if isinstance(p, list) else p for p in pages]
    result = RaindropClient(token='secret', transport=transport).fetch(
        source=RaindropSourceConfig(URL), cursor=cursor)
    return result, transport


def test_first_fetch_keeps_one_but_records_all_tied_ids():
    result, transport = fetch([[item(i, 1) for i in range(1, 51)], [item(51, 1), item(52)]])
    assert [a.id for a in result.articles] == ['1']
    assert result.next_cursor.boundary_ids == frozenset(map(str, range(1, 52)))
    assert result.next_cursor.last_fetched == BASE + timedelta(days=1)
    assert transport.get.call_count == 2
    args = transport.get.call_args
    assert args.args == (API_ROOT + '12',)
    assert args.kwargs['params'] == {'sort': '-created', 'page': 1, 'perpage': 50, 'nested': 'false'}
    assert args.kwargs['headers']['Authorization'] == 'Bearer secret'


@pytest.mark.parametrize('count', [0, 1, 50, 51, 100, 120])
def test_normal_pages_and_empty_cursor(count):
    entries = [item(i, 1) for i in range(1, count + 1)]
    pages = [entries[i:i+50] for i in range(0, count, 50)]
    if count % 50 == 0:
        pages.append([])
    cursor = RaindropCursor(BASE, frozenset())
    result, _ = fetch(pages, cursor)
    assert len(result.articles) == count
    assert result.next_cursor.last_fetched == (BASE + timedelta(days=1) if count else BASE)


def test_raises_when_new_items_exceed_page_cap():
    entries = [item(i, 1) for i in range(1, 161)]  # 満杯ページが続き自然終了しない
    pages = [entries[i:i+50] for i in range(0, 160, 50)]
    with pytest.raises(SourceFetchError, match='多すぎます'):
        fetch(pages, RaindropCursor(BASE, frozenset()))


def test_initial_empty_and_boundary_recovery():
    assert fetch([[]])[0].next_cursor is None
    cursor = RaindropCursor(BASE, frozenset({'1'}))
    result, _ = fetch([[item(1), item(2), item(2), item(3, -1)]], cursor)
    assert [a.id for a in result.articles] == ['2']
    assert result.next_cursor.boundary_ids == frozenset({'1', '2'})


def test_cross_page_duplicates():
    result, _ = fetch([[item(i, 1) for i in range(1, 51)], [item(50, 1), item(51, 1)]], RaindropCursor(BASE, frozenset()))
    assert len(result.articles) == 51


@pytest.mark.parametrize('excerpt', ['', '  ', None, '記事1', 'https://example.com/a'])
def test_title_only(excerpt):
    article = fetch([[item(1, excerpt=excerpt)]])[0].articles[0]
    assert article.content is None
    assert article.content_kind == 'none'
    assert article.published_at is None
    assert article.saved_at == BASE


def test_timezone_and_title_fallback():
    entry = item(1)
    entry.update(created='2026-09-01T09:00:00+09:00', title=' ')
    article = fetch([[entry]])[0].articles[0]
    assert article.saved_at == BASE
    assert article.title == entry['link']


@pytest.mark.parametrize('bad', [{'result': False, 'items': []}, {'result': True},
    {'result': True, 'items': [{}]}, {'result': True, 'items': [item(1) | {'created': '2026-01-01'}]},
    {'result': True, 'items': [item(1) | {'link': None}]}])
def test_malformed_response(bad):
    with pytest.raises(SourceFetchError):
        fetch([bad])


def test_partial_failure_returns_no_batch():
    with pytest.raises(SourceFetchError):
        fetch([[item(i, 1) for i in range(1, 51)], SourceFetchError('失敗')], RaindropCursor(BASE, frozenset()))


def transport_with(results):
    slept = []
    opener = Mock()
    opener.open.side_effect = results
    return UrllibJsonGetTransport(opener=opener, sleep=slept.append), opener, slept


def response():
    return io.BytesIO(json.dumps({'result': True, 'items': []}).encode())


@pytest.mark.parametrize('code', [500, 502, 503, 429])
def test_retries_transient_error_then_succeeds(code):
    transport, opener, slept = transport_with([HTTPError(API_ROOT+'12', code, '秘密', {}, None), response()])
    assert transport.get(API_ROOT+'12', params={'page': 0}, headers={'Authorization': 'Bearer secret'})['result']
    assert slept == [1]  # 指数バックオフ 2**0
    for call in opener.open.call_args_list:
        assert call.args[0].get_method() == 'GET'
        assert call.args[0].full_url == API_ROOT + '12?page=0'
        assert call.kwargs['timeout'] == 30


@pytest.mark.parametrize('code', [301, 400, 401, 403, 404])
def test_no_retry_or_secret_on_permanent_error(code):
    transport, opener, _ = transport_with([HTTPError(API_ROOT+'12', code, 'secret', {}, None)])
    with pytest.raises(SourceFetchError) as exc:
        transport.get(API_ROOT+'12', params={}, headers={})
    assert 'secret' not in str(exc.value)
    assert opener.open.call_count == 1


def test_retry_limit_and_malformed_json():
    # タイムアウト・5xx は3回まで試し、超えたら打ち切る（回数上限のみ）
    transport, opener, slept = transport_with([HTTPError(API_ROOT+'12', 500, 'secret', {}, None)] * 3)
    with pytest.raises(SourceFetchError, match='再試行上限'):
        transport.get(API_ROOT+'12', params={}, headers={})
    assert opener.open.call_count == 3
    assert slept == [1, 2]
    transport, opener, _ = transport_with([URLError('secret')] * 3)
    with pytest.raises(SourceFetchError):
        transport.get(API_ROOT+'12', params={}, headers={})
    assert opener.open.call_count == 3
    transport, opener, _ = transport_with([io.BytesIO(b'not-json')])
    with pytest.raises(SourceFetchError):
        transport.get(API_ROOT+'12', params={}, headers={})
    assert opener.open.call_count == 1


def test_redirect_and_arbitrary_destination_are_rejected():
    assert _NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com') is None
    transport, opener, _ = transport_with([])
    with pytest.raises(SourceFetchError):
        transport.get('https://example.com', params={}, headers={})
    opener.open.assert_not_called()


def test_no_progress_is_error_and_initial_newer_insertion_is_deferred():
    first = [item(i, 1) for i in range(1, 51)]
    with pytest.raises(SourceFetchError, match='進みません'):
        fetch([first, first])
    result, _ = fetch([first, [item(100, 2), item(51, 1), item(52)]])
    assert [a.id for a in result.articles] == ['1']
    assert result.next_cursor.last_fetched == BASE + timedelta(days=1)
    assert '100' not in result.next_cursor.boundary_ids


def test_empty_and_invalid_token():
    for token in (' ', 'secret\nvalue'):
        with pytest.raises(SourceFetchError):
            RaindropClient(token=token, transport=Mock())
