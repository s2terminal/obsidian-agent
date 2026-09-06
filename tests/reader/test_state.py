import pytest
import yaml

from reader.feed import validate_feeds, load_feeds
from reader.sources import source_type, raindrop_url
from reader.state import cursor_from_state, load_state, save_state, reader_lock

URL = 'https://app.raindrop.io/my/12'


@pytest.mark.parametrize('raw, expected', [
    (' https://APP.RAINDROP.IO/my/0012/ ', 12),
    ('https://app.raindrop.io/my/0', 0), ('https://app.raindrop.io/my/-1', -1)])
def test_url(raw, expected):
    source = validate_feeds({'feeds': [{'url': raw}]})['feeds'][0]
    assert source_type(source) == 'raindrop'
    assert raindrop_url(source['url']) == (f'https://app.raindrop.io/my/{expected}', expected)


@pytest.mark.parametrize('suffix', ['-99', '12/item/3', '12?q=a', '12#x', '', 'abc'])
def test_invalid_url(suffix):
    with pytest.raises(ValueError):
        validate_feeds({'feeds': [{'url': f'https://app.raindrop.io/my/{suffix}'}]})


def test_duplicate_canonical_url():
    with pytest.raises(ValueError):
        validate_feeds({'feeds': [{'url': URL}, {'url': URL + '/'}]})


def test_save_preserves_other_state_and_config(tmp_path):
    config = tmp_path / 'feed.md'
    config.write_text('```yaml\nfeeds:\n- url: ' + URL + '\n  後で読む: null\n```')
    original = config.read_bytes()
    (tmp_path / 'status.yaml').write_text('feeds: {a: {last_fetched: old}}\nraindrop: {}\ncustom: 42\n')
    state = load_state(tmp_path)
    state['raindrop'][URL] = {'items': {}, 'boundary_ids': []}
    save_state(tmp_path, state)
    assert load_state(tmp_path)['custom'] == 42
    assert load_state(tmp_path)['feeds']['a']['last_fetched'] == 'old'
    assert 'version' not in load_state(tmp_path)
    assert load_feeds(tmp_path)['feeds'][0]['_state']['items'] == {}
    assert config.read_bytes() == original


@pytest.mark.parametrize('bad', [None, [], 'text', 42])
def test_non_mapping_state_is_not_overwritten(tmp_path, bad):
    """マージも上書きも安全にできない非マッピングだけは拒否し、ファイルを残す。"""
    path = tmp_path / 'status.yaml'
    path.write_text(yaml.safe_dump(bad))
    original = path.read_bytes()
    with pytest.raises(ValueError):
        load_state(tmp_path)
    with pytest.raises(ValueError):
        save_state(tmp_path, bad)
    assert path.read_bytes() == original


@pytest.mark.parametrize('imperfect, check', [
    ({'feeds': {}}, lambda s: s['raindrop'] == {}),
    ({'raindrop': {}}, lambda s: s['feeds'] == {}),
    ({'feeds': {}, 'raindrop': []}, lambda s: s['raindrop'] == {}),
    ({'feeds': {}, 'raindrop': {URL: {}}}, lambda s: s['raindrop'][URL] == {'items': {}, 'boundary_ids': []}),
    ({'feeds': {}, 'raindrop': {URL: {'items': {}}}}, lambda s: s['raindrop'][URL]['boundary_ids'] == []),
    # 不正な last_fetched は初回扱いへ（黙って既定値で続行する）
    ({'feeds': {}, 'raindrop': {URL: {'last_fetched': '2026-01-01', 'items': {}, 'boundary_ids': []}}},
     lambda s: cursor_from_state(s['raindrop'][URL]) is None),
])
def test_imperfect_state_loads_with_defaults(tmp_path, imperfect, check):
    (tmp_path / 'status.yaml').write_text(yaml.safe_dump(imperfect))
    state = load_state(tmp_path)
    assert check(state)
    save_state(tmp_path, state)  # 正規化済みなので保存も通る


def test_lock_excludes_second_holder_and_releases(tmp_path):
    with reader_lock(tmp_path):
        with pytest.raises(RuntimeError, match='実行中'):
            with reader_lock(tmp_path):
                pytest.fail('多重実行')
    with reader_lock(tmp_path):
        pass


def test_new_state_has_only_current_namespaces(tmp_path):
    state = load_state(tmp_path)
    assert state == {'feeds': {}, 'raindrop': {}}
    save_state(tmp_path, state)
    assert yaml.safe_load((tmp_path / 'status.yaml').read_text()) == state
