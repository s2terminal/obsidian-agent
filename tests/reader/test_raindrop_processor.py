from datetime import timedelta
from unittest.mock import Mock, AsyncMock

import pytest

from reader import main as main_module
from reader.feed import load_feeds
from reader.models import SourceFetchError
from reader.raindrop_processor import process_raindrop, mark_output_done
from reader.state import load_state, save_state
from tests.reader.test_raindrop import URL, BASE, item


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv('OBSIDIAN_ROOT', str(tmp_path))
    monkeypatch.setenv('OBSIDIAN_AGENT_DIR', 'settings')
    monkeypatch.setenv('RAINDROP_ACCESS_TOKEN', 'secret')
    monkeypatch.setenv('TIMEZONE', 'Asia/Tokyo')
    directory = tmp_path / 'settings'
    directory.mkdir()
    (directory / 'feed.md').write_text('```yaml\nfeeds:\n- url: ' + URL + '\n  importance: low\n```')
    return directory


def transport(entries):
    return Mock(get=Mock(return_value={'result': True, 'items': entries}))


def source():
    return load_feeds()['feeds'][0]


async def test_initial_one_and_title_only_never_calls_llm(storage):
    summarize = AsyncMock()
    articles, errors = await process_raindrop(None, source(), summarize=summarize,
        transport=transport([item(1, 1, ''), item(2)]))
    summarize.assert_not_called()
    assert not errors and len(articles) == 1
    state = load_state(storage)['raindrop'][URL]
    assert list(state['items']) == ['1']
    assert state['items']['1']['status'] == 'ready'
    assert state['last_fetched'] == (BASE + timedelta(days=1)).isoformat()
    mark_output_done(articles)
    assert load_state(storage)['raindrop'][URL]['items']['1']['status'] == 'done'


async def test_backlog_limit_and_retry_without_api_item(storage):
    save_state(storage, {'feeds': {}, 'raindrop': {URL: {
        'last_fetched': BASE.isoformat(), 'boundary_ids': [], 'items': {}}}})
    summarize = AsyncMock(return_value='要約')
    articles, _ = await process_raindrop(None, source(), summarize=summarize,
        transport=transport([item(i, 1) for i in range(1, 8)]))
    assert len(articles) == 5
    assert summarize.await_args.kwargs == {'importance': 'low', 'content_kind': 'excerpt'}
    assert len(load_state(storage)['raindrop'][URL]['items']) == 7
    mark_output_done(articles)
    failed_api = Mock(get=Mock(side_effect=SourceFetchError('取得失敗')))
    articles, errors = await process_raindrop(None, source(), summarize=summarize, transport=failed_api)
    assert len(articles) == 2 and errors
    assert {a['_raindrop_id'] for a in articles} == {'6', '7'}


async def test_summary_failure_keeps_cursor_and_retries(storage):
    summarize = AsyncMock(side_effect=RuntimeError('secret'))
    articles, errors = await process_raindrop(None, source(), summarize=summarize, transport=transport([item(1)]))
    assert not articles and 'secret' not in str(errors)
    state = load_state(storage)['raindrop'][URL]
    assert state['last_fetched'] == BASE.isoformat()
    assert state['items']['1']['status'] == 'pending'
    assert state['items']['1']['last_attempted_at']
    summarize = AsyncMock(return_value='再試行の要約')
    articles, _ = await process_raindrop(None, source(), summarize=summarize, transport=transport([]))
    assert len(articles) == 1


async def test_preview_does_not_change_any_persisted_data(storage):
    original = {p.name: p.read_bytes() for p in storage.iterdir()}
    feed = source()
    articles, _ = await process_raindrop(None, feed, summarize=AsyncMock(return_value='要約'),
        transport=transport([item(1)]), summarize_only=True)
    assert len(articles) == 1
    assert {p.name: p.read_bytes() for p in storage.iterdir()} == original


async def test_fetch_failure_does_not_advance_or_create_state(storage):
    bad = Mock(get=Mock(side_effect=SourceFetchError('取得失敗')))
    articles, errors = await process_raindrop(None, source(), summarize=AsyncMock(), transport=bad)
    assert errors and not articles
    assert not (storage / 'status.yaml').exists()


async def test_persist_failure_stops_before_summary(storage, monkeypatch):
    monkeypatch.setattr('reader.raindrop_processor.save_state', Mock(side_effect=OSError('保存失敗')))
    summarize = AsyncMock()
    with pytest.raises(OSError):
        await process_raindrop(None, source(), summarize=summarize, transport=transport([item(1)]))
    summarize.assert_not_called()


async def test_main_output_failure_keeps_ready_for_next_run(storage, monkeypatch):
    monkeypatch.setattr(main_module, 'UrllibJsonGetTransport', lambda: transport([item(1)]))
    summarize = AsyncMock(return_value='要約')
    monkeypatch.setattr(main_module, 'summarize', summarize)
    monkeypatch.setattr(main_module, 'notify_slack', Mock())
    monkeypatch.setattr(main_module, 'write_news', Mock(side_effect=OSError('出力失敗')))
    with pytest.raises(OSError):
        await main_module.main()
    assert load_state(storage)['raindrop'][URL]['items']['1']['status'] == 'ready'
    assert summarize.await_count == 1
    from reader.writer import write_news
    monkeypatch.setattr(main_module, 'write_news', write_news)
    monkeypatch.setattr(main_module, 'build_obsidian_open_url', lambda _: 'obsidian://test')
    await main_module.main()
    assert summarize.await_count == 1
    state = load_state(storage)['raindrop'][URL]
    assert state['items']['1']['status'] == 'done'
    text = next((storage.parent / 'ai-generated' / 'feed').rglob('*.md')).read_text()
    assert '抜粋の要約' in text and '保存日' in text


async def test_missing_token_still_processes_rss(storage, monkeypatch):
    monkeypatch.delenv('RAINDROP_ACCESS_TOKEN')
    (storage / 'feed.md').write_text('```yaml\nfeeds:\n- url: ' + URL + '\n- url: https://example.com/rss\n```')
    rss = AsyncMock(return_value=([], []))
    monkeypatch.setattr(main_module, 'process_feed', rss)
    notify = Mock()
    monkeypatch.setattr(main_module, 'notify_slack', notify)
    await main_module.main()
    rss.assert_awaited_once()
    assert 'トークン' in notify.call_args.args[0]


async def test_empty_initial_remains_initial(storage):
    await process_raindrop(None, source(), summarize=AsyncMock(), transport=transport([]))
    assert 'last_fetched' not in load_state(storage)['raindrop'][URL]
    articles, _ = await process_raindrop(None, source(), summarize=AsyncMock(return_value='要約'),
        transport=transport([item(1, 1), item(2)]))
    assert len(articles) == 1


async def test_initial_ignores_large_limit_and_does_not_backfill_ties(storage):
    feed = source() | {'max_articles': 10}
    entries = [item(1), item(2), item(3, -1)]
    articles, _ = await process_raindrop(None, feed, summarize=AsyncMock(return_value='要約'), transport=transport(entries))
    assert len(articles) == 1
    mark_output_done(articles)
    articles, _ = await process_raindrop(None, source(), summarize=AsyncMock(), transport=transport(entries))
    assert not articles
    assert set(load_state(storage)['raindrop'][URL]['items']) == {'1'}


async def test_main_preview_is_read_only_and_inactive_source_skipped(storage, monkeypatch):
    monkeypatch.setattr(main_module, 'UrllibJsonGetTransport', lambda: transport([item(1, excerpt='')]))
    summarize = AsyncMock()
    notify = Mock()
    monkeypatch.setattr(main_module, 'summarize', summarize)
    monkeypatch.setattr(main_module, 'notify_slack', notify)
    original = {p: p.read_bytes() for p in storage.rglob('*') if p.is_file()}
    await main_module.main(summarize_only=True)
    assert {p: p.read_bytes() for p in storage.rglob('*') if p.is_file()} == original
    summarize.assert_not_called()
    notify.assert_not_called()
    (storage / 'feed.md').write_text('```yaml\nfeeds:\n- url: ' + URL + '\n  active: false\n```')
    processor = AsyncMock()
    monkeypatch.setattr(main_module, 'process_raindrop', processor)
    monkeypatch.delenv('RAINDROP_ACCESS_TOKEN')
    await main_module.main()
    processor.assert_not_called()


async def test_inactive_raindrop_feed_omits_pending_line(storage, monkeypatch):
    save_state(storage, {'feeds': {}, 'raindrop': {URL: {
        'last_fetched': BASE.isoformat(), 'boundary_ids': [],
        'items': {'9': {'title': 't', 'link': 'https://example.com/9', 'content': 'c',
                        'saved_at': BASE.isoformat(), 'status': 'pending', 'summary': None}}}}})
    (storage / 'feed.md').write_text('```yaml\nfeeds:\n- url: ' + URL + '\n  active: false\n```')
    notify = Mock()
    monkeypatch.setattr(main_module, 'notify_slack', notify)
    await main_module.main()
    assert '未処理' not in notify.call_args.args[0]


async def test_mixed_sources_preserve_both_namespaces(storage, monkeypatch):
    (storage / 'feed.md').write_text('```yaml\nfeeds:\n- url: ' + URL + '\n- url: https://example.com/rss\n```')
    monkeypatch.setattr(main_module, 'UrllibJsonGetTransport', lambda: transport([item(1, excerpt='')]))
    monkeypatch.setattr(main_module, 'process_feed', AsyncMock(return_value=([{
        'title': 'RSS記事', 'link': 'https://example.com/a', 'summary': 'RSS要約', 'published': '2026/09/01',
        'feed_title': 'RSS', 'feed_link': 'https://example.com/rss'}], [])))
    monkeypatch.setattr(main_module, 'notify_slack', Mock())
    monkeypatch.setattr(main_module, 'build_obsidian_open_url', lambda _: 'obsidian://test')
    await main_module.main()
    state = load_state(storage)
    assert 'last_fetched' in state['feeds']['https://example.com/rss']
    entry = state['raindrop'][URL]['items']['1']
    assert entry['status'] == 'done'
    output = next((storage.parent / 'ai-generated' / 'feed').rglob('*.md')).read_text()
    assert 'RSS記事' in output and '記事1' in output
