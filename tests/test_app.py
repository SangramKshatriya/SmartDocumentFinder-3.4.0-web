import sys

import pytest

pytest.importorskip("PySide6")

from app import parse_args, resolve_folder


def test_resolve_folder_accepts_existing_path(tmp_path):
    assert resolve_folder(str(tmp_path)) == str(tmp_path.resolve())


def test_resolve_folder_uses_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("DOCUMENT_FOLDER", str(tmp_path))
    assert resolve_folder(None) == str(tmp_path.resolve())


def test_parse_args(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["app.py", "docs", "--reindex"])
    args = parse_args()
    assert args.folder == "docs"
    assert args.reindex is True
