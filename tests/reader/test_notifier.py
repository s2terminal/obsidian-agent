from unittest.mock import MagicMock, patch

from reader.notifier import notify_slack


class TestNotifySlack:
    @patch("reader.notifier.urllib.request.urlopen")
    def test_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        notify_slack("test message", webhook_url="https://hooks.slack.com/test")
        mock_urlopen.assert_called_once()

    @patch("reader.notifier.urllib.request.urlopen")
    def test_failure_does_not_raise(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("Network error")
        # Should not raise
        notify_slack("test message", webhook_url="https://hooks.slack.com/test")
