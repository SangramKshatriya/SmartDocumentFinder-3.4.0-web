import builtins
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from services import tts_player


def test_play_audio_file_missing_path_raises():
    with pytest.raises(FileNotFoundError):
        tts_player.play_audio_file("/definitely/missing.wav")


def test_play_audio_file_windows_path_uses_winsound(tmp_path, monkeypatch):
    """Verify the Windows playback branch without using the real speaker."""
    path = tmp_path / "audio.wav"
    path.write_bytes(b"RIFF")

    play_sound = Mock()

    fake_winsound = SimpleNamespace(
        SND_FILENAME=1,
        SND_ASYNC=2,
        PlaySound=play_sound,
    )

    monkeypatch.setitem(
        sys.modules,
        "winsound",
        fake_winsound,
    )

    tts_player.play_audio_file(str(path))

    play_sound.assert_called_once_with(
        str(path),
        fake_winsound.SND_FILENAME | fake_winsound.SND_ASYNC,
    )


def test_play_audio_file_reports_non_windows_limitation(
    tmp_path,
    monkeypatch,
):
    """Force the non-Windows branch so this test works on every OS."""
    path = tmp_path / "audio.wav"
    path.write_bytes(b"RIFF")

    real_import = builtins.__import__

    def import_without_winsound(name, *args, **kwargs):
        if name == "winsound":
            raise ImportError("winsound unavailable")

        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(
        builtins,
        "__import__",
        import_without_winsound,
    )

    with pytest.raises(
        RuntimeError,
        match="Windows only",
    ):
        tts_player.play_audio_file(str(path))