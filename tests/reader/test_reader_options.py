from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from typer.testing import CliRunner

from reader import main as reader_main
from reader.checker import check
from reader.config import get_raindrop_access_token
from reader.summarizer import _summary_writer_instruction
from reader.writer import write_news, render_news


@pytest.mark.parametrize('value', ['', '   ', 'a\nb'])
def test_blank_or_invalid_token(value, monkeypatch):
    monkeypatch.setenv('RAINDROP_ACCESS_TOKEN', value)
    with pytest.raises(ValueError):
        get_raindrop_access_token()


def test_checker_does_not_require_or_show_token(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv('RAINDROP_ACCESS_TOKEN', raising=False)
    monkeypatch.setenv('OBSIDIAN_ROOT', str(tmp_path))
    monkeypatch.setenv('OBSIDIAN_AGENT_DIR', '.')
    (tmp_path / 'feed.md').write_text('```yaml\nfeeds:\n- 後で読む:\n  url: https://app.raindrop.io/my/0\n```')
    check()
    output = capsys.readouterr().out
    assert 'raindrop' in output and 'collection   : 0' in output and 'pending      : 0' in output
    assert 'TOKEN' not in output
    assert not (tmp_path / 'status.yaml').exists()


async def test_preview_rss_cache_is_unchanged(tmp_path, monkeypatch):
    from reader.cache import save_cache, load_cache, cache_path
    url = 'https://example.com/rss'
    save_cache(url, {'1': {'title': '再試行', 'link': 'https://example.com/a', 'content': '本文'}}, tmp_path)
    original = cache_path(url, tmp_path).read_bytes()
    monkeypatch.setattr(reader_main, 'load_cache', lambda url: load_cache(url, tmp_path))
    save = Mock()
    monkeypatch.setattr(reader_main, 'save_cache', save)
    monkeypatch.setattr(reader_main, 'summarize', AsyncMock(return_value='要約'))
    monkeypatch.setattr('reader.sources.rss.feedparser.parse', lambda _: SimpleNamespace(
        bozo=False, entries=[{'id': '1'}], feed=SimpleNamespace(title='配信', link=url)))
    articles, _ = await reader_main.process_feed(None, {'url': url}, summarize_only=True)
    assert len(articles) == 1
    save.assert_not_called()
    assert cache_path(url, tmp_path).read_bytes() == original


def test_excerpt_instruction_does_not_invent_missing_details():
    text = _summary_writer_instruction(SimpleNamespace(state={'content_kind': 'excerpt', 'summary_format': 'bullet_list'}))
    assert '情報を補わない' in text
    assert '5W1Hをできるだけ明確に' not in text


def test_title_only_output_and_atomic_failure(tmp_path, monkeypatch):
    monkeypatch.setenv('TIMEZONE', 'Asia/Tokyo')
    articles = [{'title': '題名', 'link': 'https://example.com/a', 'summary': None, 'published': '2026/09/01',
                 'feed_title': '後で読む（保存日）', 'feed_link': 'https://app.raindrop.io/my/0'}]
    assert 'None' not in render_news(articles)
    path = write_news(articles, tmp_path)
    original = path.read_bytes()
    monkeypatch.setattr('reader.state.os.replace', Mock(side_effect=OSError('置換失敗')))
    with pytest.raises(OSError):
        write_news(articles, tmp_path)
    assert path.read_bytes() == original
    assert list(path.parent.iterdir()) == [path]


def test_cli_describes_all_sources():
    import main
    result = CliRunner().invoke(main.app, ['reader', '--help'])
    assert result.exit_code == 0
    assert 'Raindrop' in result.stdout
