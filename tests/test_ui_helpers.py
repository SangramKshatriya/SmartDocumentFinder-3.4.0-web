import os

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ui.history_dialog import format_timestamp
from ui.login_dialog import LoginDialog


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    return app


def test_format_timestamp_handles_iso_and_empty():
    assert format_timestamp("") == "—"
    value = format_timestamp("2026-10-01T10:00:00+00:00")
    assert "2026" in value
    assert "01 Oct" in value


def test_login_dialog_rejects_blank_username(qapp, monkeypatch):
    calls = []
    monkeypatch.setattr("ui.login_dialog.record_login_attempt", lambda **kwargs: calls.append(kwargs))
    dialog = LoginDialog()
    dialog._accept()
    assert dialog.message.text() == "Username is required."
    assert calls[0]["status"] == "FAIL"
