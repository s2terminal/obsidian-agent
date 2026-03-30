from pathlib import Path

import yaml

from .config import get_feed_yaml


def load_feeds(feed_yaml: Path | None = None) -> dict:
    path = feed_yaml or get_feed_yaml()
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_feeds(data: dict, feed_yaml: Path | None = None):
    path = feed_yaml or get_feed_yaml()
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
