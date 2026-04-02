"""Unit-Tests für AdminNotifier."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mdal.config import NotifierConfig
from mdal.notifier import AdminNotifier


def make_notifier(tmp_path: Path, webhook_url: str | None = None) -> AdminNotifier:
    log_path = str(tmp_path / "admin.log")
    return AdminNotifier(NotifierConfig(log_path=log_path, webhook_url=webhook_url))


class TestAdminNotifierLog:
    def test_escalation_writes_jsonl(self, tmp_path):
        notifier = make_notifier(tmp_path)
        notifier.notify_escalation(
            session_id="sess-1",
            retry_count=3,
            last_error="Stilregel-Verletzung",
        )
        lines = (tmp_path / "admin.log").read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["event_type"] == "escalation"
        assert entry["session_id"] == "sess-1"
        assert entry["retry_count"] == 3
        assert "timestamp" in entry

    def test_capability_asymmetry_writes_jsonl(self, tmp_path):
        notifier = make_notifier(tmp_path)
        notifier.notify_capability_asymmetry(
            session_id="sess-2",
            language="de",
            details="Stil nicht reproduzierbar",
        )
        lines = (tmp_path / "admin.log").read_text(encoding="utf-8").strip().splitlines()
        entry = json.loads(lines[0])
        assert entry["event_type"] == "capability_asymmetry"
        assert entry["language"] == "de"

    def test_multiple_events_append(self, tmp_path):
        notifier = make_notifier(tmp_path)
        notifier.notify_escalation("s1", 3, "err1")
        notifier.notify_escalation("s2", 2, "err2")
        lines = (tmp_path / "admin.log").read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2

    def test_log_directory_created_if_missing(self, tmp_path):
        subdir = tmp_path / "nested" / "deep"
        notifier = AdminNotifier(
            NotifierConfig(log_path=str(subdir / "admin.log"))
        )
        notifier.notify_escalation("s", 1, "e")
        assert (subdir / "admin.log").exists()

    def test_no_log_path_logs_warning_but_does_not_raise(self, caplog):
        import logging
        notifier = AdminNotifier(NotifierConfig())
        with caplog.at_level(logging.WARNING, logger="mdal.notifier"):
            notifier.notify_escalation("s", 1, "e")
        assert any("kein log_path" in r.message for r in caplog.records)


class TestAdminNotifierWebhook:
    def test_webhook_called_with_correct_payload(self, tmp_path):
        notifier = make_notifier(tmp_path, webhook_url="http://example.invalid/hook")
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__  = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response

            notifier.notify_escalation("s", 3, "err")

            mock_client.post.assert_called_once()
            _, kwargs = mock_client.post.call_args
            payload = kwargs["json"]
            assert payload["event_type"] == "escalation"

    def test_webhook_failure_does_not_raise(self, tmp_path):
        notifier = make_notifier(tmp_path, webhook_url="http://example.invalid/hook")
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__  = MagicMock(return_value=False)
            mock_client.post.side_effect = Exception("connection refused")

            # Darf nicht werfen
            notifier.notify_escalation("s", 1, "err")

    def test_no_webhook_url_skips_http_call(self, tmp_path):
        notifier = make_notifier(tmp_path, webhook_url=None)
        with patch("httpx.Client") as mock_client_cls:
            notifier.notify_escalation("s", 1, "err")
            mock_client_cls.assert_not_called()
