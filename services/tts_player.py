from pathlib import Path


def play_audio_file(path: str) -> None:
    path_obj = Path(path)
    if not path_obj.is_file():
        raise FileNotFoundError(path)
    try:
        import winsound
        winsound.PlaySound(str(path_obj), winsound.SND_FILENAME | winsound.SND_ASYNC)
        return
    except ImportError:
        pass
    raise RuntimeError("Audio playback is currently implemented for Windows only.")
