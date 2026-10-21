import os

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("speech_recognition")

from ui.voice_assistant import VoiceWorker


def test_rms_raw_detects_signal_level():
    raw = b"\x00\x00" * 100 + b"\xff\x7f" * 100
    assert VoiceWorker._rms_raw(raw) > 0
    assert VoiceWorker._rms_raw(b"") == 0.0


def test_provider_modes():
    worker = VoiceWorker()
    sarvam = type("Provider", (), {"name": "sarvam"})()
    other = type("Provider", (), {"name": "other"})()
    assert worker._provider_modes(sarvam) == ("translate", "codemix", "transcribe")
    assert worker._provider_modes(other) == ("transcribe",)


def test_float_env_validation(monkeypatch):
    monkeypatch.setenv("VOICE_LISTEN_TIMEOUT", "0.1")
    assert VoiceWorker._float_env("VOICE_LISTEN_TIMEOUT", 2.0, minimum=0.5) == 2.0
    monkeypatch.setenv("VOICE_LISTEN_TIMEOUT", "not-a-number")
    assert VoiceWorker._float_env("VOICE_LISTEN_TIMEOUT", 2.0) == 2.0

def test_rms_raw_handles_odd_length_bytes():
    assert VoiceWorker._rms_raw(b"\x00\x00\xff") >= 0.0


def test_provider_recognition_prefers_translation_for_sarvam(tmp_path):
    class Provider:
        name = "sarvam"
        def __init__(self):
            self.calls = []
        def speech_to_text(self, path, language_code=None, mode="transcribe"):
            self.calls.append((path, language_code, mode))
            return {
                "transcript": "show my PAN card" if mode == "translate" else "",
                "language_code": "hi-IN",
            }

    worker = VoiceWorker()
    provider = Provider()
    wav = tmp_path / "sample.wav"
    wav.write_bytes(b"RIFF")
    text, language, error = worker._recognize_with_provider(provider, wav)
    assert text == "show my PAN card"
    assert language == "hi-IN"
    assert error == ""
    assert provider.calls[0][2] == "translate"


def test_provider_recognition_reports_empty_transcript(tmp_path):
    class Provider:
        name = "sarvam"
        def speech_to_text(self, *args, **kwargs):
            return {"transcript": "", "language_code": "hi-IN"}

    worker = VoiceWorker()
    wav = tmp_path / "sample.wav"
    wav.write_bytes(b"RIFF")
    text, language, error = worker._recognize_with_provider(Provider(), wav)
    assert text == ""
    assert language == ""
    assert "empty transcript" in error.lower()
