import json
import urllib.parse
import urllib.request

from reader.config import get_slack_webhook_url


def notify_slack(message: str, webhook_url: str | None = None):
    """Slack Webhook で通知を送信する。"""
    url = webhook_url or get_slack_webhook_url()
    payload = json.dumps({"text": message})
    data = urllib.parse.urlencode({"payload": payload}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = getattr(resp, "status", None)
            if status is None or not (200 <= status < 300):
                raise RuntimeError(f"Slack通知送信失敗: HTTPステータスコード {status}")
            print(f"Slack通知送信完了 (status={status})")
    except Exception as e:
        print(f"Slack通知送信失敗: {e}")
