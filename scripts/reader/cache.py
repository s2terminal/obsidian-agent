import hashlib
import json
from pathlib import Path

from .config import CACHE_DIR


def cache_path(feed_url: str, cache_dir: Path = CACHE_DIR) -> Path:
    return cache_dir / (hashlib.sha256(feed_url.encode()).hexdigest() + ".json")


def load_cache(feed_url: str, cache_dir: Path = CACHE_DIR) -> dict[str, dict]:
    """キャッシュを読み込む。各エントリはリトライ対象の記事データを持つ。"""
    p = cache_path(feed_url, cache_dir)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 旧形式(リスト)は処理済みなので無視
            if isinstance(data, list):
                return {}
            # 旧形式の status 付きエントリを移行
            migrated = {}
            for eid, entry in data.items():
                status = entry.get("status")
                if status in ("done", "skipped"):
                    continue
                migrated[eid] = {k: v for k, v in entry.items() if k != "status"}
            return migrated
    return {}


def save_cache(feed_url: str, cache: dict[str, dict], cache_dir: Path = CACHE_DIR):
    cache_dir.mkdir(parents=True, exist_ok=True)
    with open(cache_path(feed_url, cache_dir), "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
