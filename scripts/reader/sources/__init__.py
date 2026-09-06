"""ソース種別と Raindrop コレクション URL の検証。"""
import re
from urllib.parse import urlsplit

from reader.sources.markdown import is_markdown_feed


def raindrop_url(url: str) -> tuple[str, int]:
    parsed = urlsplit(url.strip())
    match = re.fullmatch(r'/my/(-?[0-9]+)/?', parsed.path)
    if (parsed.scheme != 'https' or parsed.netloc.lower() != 'app.raindrop.io'
            or parsed.query or parsed.fragment or '?' in url or '#' in url or not match):
        raise ValueError('Raindropには https://app.raindrop.io/my/<ID> を指定してください')
    collection = int(match[1])
    if collection < -1:
        raise ValueError('Raindropのごみ箱や未対応コレクションは取得できません')
    return f'https://app.raindrop.io/my/{collection}', collection


def source_type(source: dict) -> str:
    explicit = source.get('type')
    if explicit is not None:
        if explicit not in {'rss', 'markdown', 'raindrop'}:
            raise ValueError('未対応のソース種別です')
        if explicit == 'raindrop':
            raindrop_url(source['url'])
        return explicit
    if urlsplit(source['url'].strip()).hostname == 'app.raindrop.io':
        raindrop_url(source['url'])
        return 'raindrop'
    return 'markdown' if is_markdown_feed(source) else 'rss'
