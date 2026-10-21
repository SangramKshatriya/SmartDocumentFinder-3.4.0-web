import pytest

from services.provider_factory import build_provider


def test_build_provider_local_mode(monkeypatch):
    monkeypatch.setenv("LANGUAGE_PROVIDER", "local")
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    assert build_provider() is None


def test_build_provider_sarvam_requires_key(monkeypatch):
    monkeypatch.setenv("LANGUAGE_PROVIDER", "sarvam")
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    assert build_provider() is None


def test_build_provider_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("LANGUAGE_PROVIDER", "unknown")
    with pytest.raises(ValueError, match="Unsupported LANGUAGE_PROVIDER"):
        build_provider()
