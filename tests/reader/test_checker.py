from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from reader import checker
from reader.checker import check
from reader.models import FetchResult, SourceArticle, SourceFetchError


def _feed_md(tmp_path, body: str) -> None:
    tmp_path.joinpath('feed.md').write_text(f'```yaml\n{body}\n```', encoding='utf-8')


@pytest.fixture
def rss_feed(tmp_path, monkeypatch):
    monkeypatch.setenv('OBSIDIAN_ROOT', str(tmp_path))
    monkeypatch.setenv('OBSIDIAN_AGENT_DIR', '.')
    _feed_md(tmp_path, 'feeds:\n- url: https://example.com/rss\n  last_fetched: 2026-03-01T00:00:00+00:00')
    return tmp_path


def _article(published_at: datetime | None) -> SourceArticle:
    return SourceArticle(
        id=str(published_at), source_key='https://example.com/rss', source_type='rss',
        title='題名', link='https://example.com/a', content='本文', content_kind='body',
        published_at=published_at, saved_at=None, display_date='2026/03/02',
    )


def test_check_without_fetch_does_not_touch_network(rss_feed, monkeypatch, capsys):
    fetch = Mock(side_effect=AssertionError('取得してはいけない'))
    monkeypatch.setattr('reader.sources.rss.fetch', fetch)
    check()
    output = capsys.readouterr().out
    assert 'フィード数: 1' in output
    assert 'fetch        :' not in output
    fetch.assert_not_called()


def test_check_fetch_counts_new_entries(rss_feed, monkeypatch, capsys):
    base = datetime(2026, 3, 1, tzinfo=timezone.utc)
    articles = [_article(base + timedelta(days=1)), _article(base + timedelta(days=2)), _article(base - timedelta(days=1))]
    monkeypatch.setattr('reader.sources.rss.fetch',
                        lambda source: FetchResult(articles, '配信名', 'https://example.com'))
    monkeypatch.setattr(checker, 'load_cache', lambda url: {'retry-1': {}})
    check(fetch=True)
    output = capsys.readouterr().out
    assert 'fetch        : 成功' in output
    assert 'source_title : 配信名' in output
    assert 'entries      : 3件' in output
    assert 'new_entries  : 2件' in output
    assert 'retry        : 1件' in output
    assert 'summarize    : 最大3件' in output
    assert not (rss_feed / 'status.yaml').exists()


def test_check_fetch_reports_failure_without_raising(rss_feed, monkeypatch, capsys):
    def _fail(source):
        raise SourceFetchError('RSSフィードの取得に失敗')
    monkeypatch.setattr('reader.sources.rss.fetch', _fail)
    check(fetch=True)
    assert 'fetch        : 失敗 (RSSフィードの取得に失敗)' in capsys.readouterr().out


def test_check_fetch_hides_details_of_non_fetch_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('OBSIDIAN_ROOT', str(tmp_path))
    monkeypatch.setenv('OBSIDIAN_AGENT_DIR', '.')
    monkeypatch.setenv('RAINDROP_ACCESS_TOKEN', 'super-secret-token')
    _feed_md(tmp_path, 'feeds:\n- 後で読む:\n  url: https://app.raindrop.io/my/0')

    def _fail(*args, **kwargs):
        raise RuntimeError('token=super-secret-token が不正です')
    monkeypatch.setattr(checker, 'RaindropClient', Mock(return_value=SimpleNamespace(fetch=_fail)))
    check(fetch=True)
    output = capsys.readouterr().out
    assert 'fetch        : 失敗 (RuntimeError)' in output
    assert 'super-secret-token' not in output


def test_check_fetch_skips_inactive_feed(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('OBSIDIAN_ROOT', str(tmp_path))
    monkeypatch.setenv('OBSIDIAN_AGENT_DIR', '.')
    _feed_md(tmp_path, 'feeds:\n- url: https://example.com/rss\n  active: false')
    monkeypatch.setattr('reader.sources.rss.fetch', Mock(side_effect=AssertionError('取得してはいけない')))
    check(fetch=True)
    assert 'fetch        :' not in capsys.readouterr().out


def test_check_summarize_runs_reader_in_summarize_only_mode(rss_feed, monkeypatch, capsys):
    run = Mock()
    monkeypatch.setattr('reader.main.run', run)
    monkeypatch.setattr('reader.sources.rss.fetch', Mock(side_effect=AssertionError('二重取得してはいけない')))
    check(fetch=True, summarize=True)
    run.assert_called_once_with(summarize_only=True)
    assert '要約ドライラン' in capsys.readouterr().out


def test_cli_check_options_replace_summarize_only():
    import main
    runner = CliRunner()
    help_result = runner.invoke(main.app, ['reader', 'check', '--help'])
    assert help_result.exit_code == 0
    assert '--fetch' in help_result.stdout and '--summarize' in help_result.stdout
    removed = runner.invoke(main.app, ['reader', '--summarize-only'])
    assert removed.exit_code != 0
