"""Capture a real microphone clip and send it to Sarvam STT.

This distinguishes microphone/audio-capture problems from Sarvam
authentication or transcription problems.

The API key is never printed.
"""

from __future__ import annotations

import math
import os
import sys
import tempfile
from array import array
from pathlib import Path

# ---------------------------------------------------------------------------
# Make the project root importable when this file is executed directly:
#
#     python scripts/test_live_sarvam_stt.py
#
# Without this, Python may only add the "scripts" directory to sys.path and
# imports such as "from services..." can fail with:
#
#     ModuleNotFoundError: No module named 'services'
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Third-party imports
# ---------------------------------------------------------------------------
from dotenv import load_dotenv
import speech_recognition as sr

# Load environment variables from the project root .env file.
load_dotenv(ROOT / ".env")

# Import project code only AFTER ROOT has been added to sys.path.
from services.provider_factory import build_provider


def rms_from_raw(raw: bytes) -> float:
    """Calculate RMS level from 16-bit PCM audio bytes."""
    if not raw:
        return 0.0

    samples = array("h")

    try:
        samples.frombytes(raw)
    except (ValueError, BufferError):
        return 0.0

    if not samples:
        return 0.0

    return math.sqrt(
        sum(sample * sample for sample in samples) / len(samples)
    )


def capture_microphone_audio() -> sr.AudioData | None:
    """Capture one speech clip from the default microphone."""
    print("=== Live Sarvam STT diagnostic ===")
    print("Speak a simple sentence such as: show my PAN card")
    print("You have 7 seconds to start speaking and up to 12 seconds to speak.\n")

    recognizer = sr.Recognizer()

    # Speech recognition tuning.
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 0.8
    recognizer.phrase_threshold = 0.2
    recognizer.non_speaking_duration = 0.4

    microphone_kwargs = {}
    device_raw = os.getenv("AUDIO_DEVICE_INDEX", "").strip()
    if device_raw:
        try:
            microphone_kwargs["device_index"] = int(device_raw)
        except ValueError:
            print(f"WARNING: Ignoring invalid AUDIO_DEVICE_INDEX={device_raw!r}")

    try:
        with sr.Microphone(**microphone_kwargs) as source:
            print("Calibrating microphone...")

            recognizer.adjust_for_ambient_noise(
                source,
                duration=0.5,
            )

            print(
                f"Energy threshold: "
                f"{recognizer.energy_threshold:.1f}"
            )

            print("LISTENING — speak now")

            audio = recognizer.listen(
                source,
                timeout=7,
                phrase_time_limit=12,
            )

            return audio

    except sr.WaitTimeoutError:
        print("ERROR: No speech started before the timeout.")
        return None

    except OSError as exc:
        print(f"ERROR: Microphone unavailable: {exc}")
        print("Run: python scripts/list_microphones.py")
        return None

    except Exception as exc:
        print(f"ERROR: Unexpected microphone error: {exc}")
        return None


def save_audio_to_wav(audio: sr.AudioData) -> Path:
    """Save captured AudioData as a temporary 16 kHz mono WAV file."""
    wav_bytes = audio.get_wav_data(
        convert_rate=16000,
        convert_width=2,
    )

    temp = tempfile.NamedTemporaryFile(
        suffix=".wav",
        delete=False,
    )

    try:
        temp.write(wav_bytes)
        temp.flush()
    finally:
        temp.close()

    return Path(temp.name)


def test_sarvam_stt(provider, wav_path: Path) -> int:
    """Send the captured WAV file to Sarvam STT."""
    # Translation-first is deliberate: the app retrieves documents, so an
    # English-normalized voice result removes the need to run a second
    # translation step before document-name extraction.
    modes = ("translate", "codemix", "transcribe")

    for mode in modes:
        print(f"Sending to Sarvam (mode={mode})...")

        try:
            response = provider.speech_to_text(
                str(wav_path),
                language_code="unknown",
                mode=mode,
            )

        except Exception as exc:
            print(
                f"ERROR: Sarvam request failed "
                f"(mode={mode}): {exc}"
            )
            continue

        # Never print sensitive credentials. The provider response itself
        # should not contain the API key, but only inspect the useful fields.
        if isinstance(response, dict):
            transcript = str(
                response.get("transcript") or ""
            ).strip()

            status = response.get("status")
            error = response.get("error")

            print("Response status:", status)

            if error:
                print("Response error:", error)

        else:
            print(
                "WARNING: Unexpected Sarvam response type:",
                type(response).__name__,
            )
            transcript = ""

        if transcript:
            print(f"SUCCESS: {transcript}")
            return 0

        print(
            f"No transcript returned for mode={mode}."
        )

    print()
    print(
        "RESULT: Sarvam accepted the audio but returned no transcript."
    )
    print(
        "The capture contained non-silent audio; "
        "inspect Sarvam configuration, language/mode, "
        "or microphone quality/input device next."
    )

    return 4


def main() -> int:
    """Run the complete microphone -> WAV -> Sarvam STT diagnostic."""
    # -----------------------------------------------------------------------
    # 1. Capture microphone audio
    # -----------------------------------------------------------------------
    audio = capture_microphone_audio()

    if audio is None:
        return 2

    # -----------------------------------------------------------------------
    # 2. Convert to raw PCM and calculate signal strength
    # -----------------------------------------------------------------------
    try:
        raw = audio.get_raw_data(
            convert_rate=16000,
            convert_width=2,
        )
    except Exception as exc:
        print(f"ERROR: Failed to process captured audio: {exc}")
        return 3

    # 16-bit audio = 2 bytes per sample.
    duration = len(raw) / (16000 * 2)
    rms = rms_from_raw(raw)

    print(
        f"Captured: {len(raw)} bytes, "
        f"{duration:.2f}s, RMS={rms:.1f}"
    )

    # -----------------------------------------------------------------------
    # 3. Check whether microphone is effectively silent
    # -----------------------------------------------------------------------
    if not raw or rms < 8:
        print(
            "ERROR: The selected microphone is effectively silent."
        )
        print(
            "Check Windows Settings > System > Sound > Input "
            "and your default microphone."
        )
        return 3

    # -----------------------------------------------------------------------
    # 4. Build Sarvam provider
    # -----------------------------------------------------------------------
    try:
        provider = build_provider()
    except Exception as exc:
        print(f"ERROR: Could not initialize Sarvam provider: {exc}")
        return 5

    # -----------------------------------------------------------------------
    # 5. Save microphone recording to a temporary WAV file
    # -----------------------------------------------------------------------
    wav_path: Path | None = None

    try:
        wav_path = save_audio_to_wav(audio)

        print(f"WAV file created: {wav_path}")

        # -------------------------------------------------------------------
        # 6. Send WAV to Sarvam STT
        # -------------------------------------------------------------------
        return test_sarvam_stt(
            provider,
            wav_path,
        )

    finally:
        # Always remove temporary audio file.
        if wav_path is not None:
            try:
                wav_path.unlink(missing_ok=True)
            except OSError as exc:
                print(
                    f"WARNING: Could not delete temporary WAV file: {exc}"
                )


if __name__ == "__main__":
    raise SystemExit(main())