"""Standalone microphone diagnostic for Smart Document Finder.

Run from the project root:
    python scripts/test_microphone.py

This checks microphone access/capture only; it does not call Sarvam, BHASHINI,
or Google and never prints API keys.
"""
from __future__ import annotations

import math
import os
from array import array
from pathlib import Path
import wave

from dotenv import load_dotenv
import speech_recognition as sr

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)


def rms(raw: bytes) -> float:
    samples = array("h")
    samples.frombytes(raw)
    if not samples:
        return 0.0
    return math.sqrt(sum(v * v for v in samples) / len(samples))


def list_devices() -> None:
    print("Available microphones:")
    for i, name in enumerate(sr.Microphone.list_microphone_names()):
        print(f"  [{i}] {name}")


def main() -> int:
    print("=== Smart Document Finder microphone test ===")
    list_devices()
    print()

    device_raw = os.getenv("AUDIO_DEVICE_INDEX", "").strip()
    device_index = None
    if device_raw:
        try:
            device_index = int(device_raw)
        except ValueError:
            print(f"Invalid AUDIO_DEVICE_INDEX={device_raw!r}; using default.")

    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 0.8
    recognizer.phrase_threshold = 0.2
    recognizer.non_speaking_duration = 0.4

    try:
        with sr.Microphone(device_index=device_index, sample_rate=16000) as source:
            print("Calibrating for ambient noise…")
            recognizer.adjust_for_ambient_noise(source, duration=0.6)
            print(f"Energy threshold: {recognizer.energy_threshold:.0f}")
            print("Speak now…")
            audio = recognizer.listen(source, timeout=8, phrase_time_limit=15)
    except sr.WaitTimeoutError:
        print("FAIL: No speech started before the timeout.")
        return 2
    except OSError as exc:
        print(f"FAIL: Microphone unavailable: {exc}")
        print("Set AUDIO_DEVICE_INDEX in .env to one of the device indexes above.")
        return 3

    raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
    duration = len(raw) / (16000 * 2)
    level = rms(raw)
    print(f"Captured: {len(raw)} bytes | {duration:.2f}s | RMS={level:.1f}")

    output = ROOT / "data" / "voice_test.wav"
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(raw)
    print(f"PASS: Saved microphone test clip to {output}")
    return 0 if level >= 20 and duration >= 0.08 else 4


if __name__ == "__main__":
    raise SystemExit(main())
