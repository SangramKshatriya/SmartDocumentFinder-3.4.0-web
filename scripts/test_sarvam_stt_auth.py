"""Minimal Sarvam STT authentication/endpoint smoke test.

Creates a 1-second silent WAV and calls /speech-to-text.  A 403 with
invalid_api_key_error means the key is not accepted by Sarvam.  A different
response means authentication reached the endpoint and the remaining error
is about the audio/request rather than credentials.
"""
from __future__ import annotations

import os
import struct
import sys
import wave
from pathlib import Path

from dotenv import load_dotenv
import requests

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

key = os.getenv("SARVAM_API_KEY", "").strip().strip("'").strip('"')
if not key:
    raise SystemExit("SARVAM_API_KEY is missing from .env")

wav_path = ROOT / "data" / ".sarvam_stt_auth_test.wav"
wav_path.parent.mkdir(exist_ok=True)
with wave.open(str(wav_path), "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(16000)
    wav.writeframes(struct.pack("<16000h", *([0] * 16000)))

try:
    with open(wav_path, "rb") as audio:
        response = requests.post(
            "https://api.sarvam.ai/speech-to-text",
            headers={"API-Subscription-Key": key},
            files={"file": (wav_path.name, audio, "audio/wav")},
            data={"model": "saaras:v4", "language_code": "unknown", "mode": "codemix"},
            timeout=45,
        )
    print(f"HTTP {response.status_code}")
    print(response.text[:1000])
    if response.status_code == 403:
        print("\nRESULT: Sarvam rejected the API key for STT. Create/rotate the key and update .env.")
        sys.exit(2)
    print("\nRESULT: Authentication reached the STT endpoint. Inspect the response above for audio/request errors.")
finally:
    wav_path.unlink(missing_ok=True)
