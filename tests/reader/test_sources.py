from datetime import datetime, timezone
from types import SimpleNamespace

from reader.sources import markdown, rss, source_type


def test_markdown_common_article_preserves_identity_and_date(monkeypatch):
    url = 'https://example.com/log.md'
    entries = markdown.parse_md_feed(url, '## September 06, 2026\n本文')
    monkeypatch.setattr(markdown, 'fetch_md_feed', lambda _: entries)
    result = markdown.fetch({'url': url, 'title': '更新'})
    article = result.articles[0]
    assert article.id == entries[0]['id']
    assert article.content == '本文'
    assert article.published_at == datetime(2026, 9, 6, tzinfo=timezone.utc)
    assert article.source_type == 'markdown'
    assert result.source_title == '更新'


def test_rss_common_article_fallback_and_explicit_type(monkeypatch):
    monkeypatch.setattr(rss.feedparser, 'parse', lambda _: SimpleNamespace(
        bozo=False, entries=[{'link': 'https://example.com/a', 'summary': '本文'}],
        feed=SimpleNamespace(title='配信', link='https://example.com')))
    result = rss.fetch({'url': 'https://example.com/rss'})
    assert result.articles[0].id == 'https://example.com/a'
    assert result.articles[0].published_at is None
    assert result.articles[0].saved_at is None
    assert source_type({'url': 'https://example.com/a.md', 'type': 'rss'}) == 'rss'
