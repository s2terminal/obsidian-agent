import hashlib
from time import struct_time

import pytest

from reader.parser import entry_content, entry_id, entry_published_date


class TestEntryId:
    @pytest.mark.parametrize(
        "entry, expected",
        [
            ({"id": "unique-id", "link": "https://example.com", "title": "Title"}, "unique-id"),
            ({"link": "https://example.com/article", "title": "Title"}, "https://example.com/article"),
            ({"title": "My Title"}, hashlib.sha256("My Title".encode()).hexdigest()),
            ({}, hashlib.sha256(b"").hexdigest()),
        ],
        ids=[
            "idフィールドがあればそれを返す",
            "idが無ければlinkにフォールバック",
            "id・linkが無ければタイトルのSHA256ハッシュ",
            "空エントリはタイトル空文字のハッシュ",
        ],
    )
    def test_entry_id(self, entry, expected):
        assert entry_id(entry) == expected


class TestEntryContent:
    def test_content_attribute(self):
        class Entry(dict):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.content = [{"value": "<p>Full content</p>"}]

        entry = Entry({"summary": "Short summary"})
        assert entry_content(entry) == "<p>Full content</p>"

    @pytest.mark.parametrize(
        "entry, expected",
        [
            ({"summary": "This is summary text"}, "This is summary text"),
            ({"description": "This is description text"}, "This is description text"),
            ({}, ""),
        ],
        ids=[
            "summaryフィールドを返す",
            "descriptionにフォールバック",
            "空エントリは空文字を返す",
        ],
    )
    def test_entry_content(self, entry, expected):
        assert entry_content(entry) == expected


class TestEntryPublishedDate:
    @pytest.mark.parametrize(
        "entry, check",
        [
            (
                {"published_parsed": struct_time((2026, 3, 15, 12, 0, 0, 6, 74, 0))},
                lambda r: r == "2026/03/15",
            ),
            (
                {"updated_parsed": struct_time((2026, 1, 10, 0, 0, 0, 4, 10, 0))},
                lambda r: r.startswith("2026/01/"),
            ),
            (
                {
                    "published_parsed": struct_time((2026, 3, 15, 12, 0, 0, 6, 74, 0)),
                    "updated_parsed": struct_time((2026, 1, 10, 8, 30, 0, 4, 10, 0)),
                },
                lambda r: r == "2026/03/15",
            ),
            (
                {},
                lambda r: "スクリプト実行日" in r,
            ),
        ],
        ids=[
            "published_parsedから日付を取得",
            "updated_parsedにフォールバック",
            "published_parsedがupdated_parsedより優先",
            "日付なしはスクリプト実行日を返す",
        ],
    )
    def test_entry_published_date(self, entry, check):
        assert check(entry_published_date(entry))
