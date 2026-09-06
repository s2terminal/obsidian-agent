"""状態の正規化、原子的保存と単一ホストのプロセス間排他。"""
import fcntl
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

import yaml

from reader.models import RaindropCursor, utc_datetime


def cursor_from_state(state: dict) -> RaindropCursor | None:
    """last_fetched があり妥当なら取得位置を返す。無い・不正なら None（初回扱い）。"""
    raw = state.get("last_fetched")
    if not raw:
        return None
    try:
        last_fetched = utc_datetime(raw)
    except ValueError:
        return None
    ids = state.get("boundary_ids")
    return RaindropCursor(last_fetched, frozenset(str(i) for i in ids) if isinstance(ids, list) else frozenset())


def normalize_state(data: object) -> dict:
    """欠損・型不一致は既定値で補い、そのまま処理を続けられる形にする。

    マージも上書きも安全にできない「マッピングでない status.yaml」だけを拒否する。
    未知のトップレベルキーや他ソースの状態はそのまま残す。
    """
    if not isinstance(data, dict):
        raise ValueError("status.yamlにはマッピングが必要です")
    for namespace in ("feeds", "raindrop"):
        if not isinstance(data.get(namespace), dict):
            data[namespace] = {}
    for url, state in list(data["raindrop"].items()):
        if not isinstance(state, dict):
            state = data["raindrop"][url] = {}
        if not isinstance(state.get("items"), dict):
            state["items"] = {}
        if not isinstance(state.get("boundary_ids"), list):
            state["boundary_ids"] = []
    return data


def load_state(directory: Path) -> dict:
    path = directory / "status.yaml"
    if not path.exists():
        return {"feeds": {}, "raindrop": {}}
    return normalize_state(yaml.safe_load(path.read_text(encoding="utf-8")))


def atomic_write(path: Path, text: str) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_state(directory: Path, data: dict) -> None:
    atomic_write(directory / "status.yaml", yaml.safe_dump(normalize_state(data), allow_unicode=True, sort_keys=False))


@contextmanager
def reader_lock(directory: Path):
    # ロックファイルを削除するとinodeが分かれるため、解放後も残す。
    with (directory / ".reader.lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Readerは既に実行中です") from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)
