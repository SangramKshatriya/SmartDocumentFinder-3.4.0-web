from __future__ import annotations

import math
import os
import tempfile
from array import array
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QThread

try:
    import speech_recognition as sr
except ImportError:
    sr = None

from services.provider_factory import build_provider


class VoiceWorker(QObject):
    """Capture microphone audio and turn it into text.

    The voice path is deliberately provider-agnostic:
    1. Capture/validate a real microphone clip with SpeechRecognition/PyAudio.
    2. Prefer the configured Sarvam/BHASHINI provider for Indian languages.
    3. Fall back to Google's SpeechRecognition backend for English/Hindi/basic
       recovery when the remote provider is unavailable.

    The important invariant is that ``audio`` is created by the microphone
    capture step before any transcription code tries to use it.
    """

    finished = Signal(str)
    language_detected = Signal(str)
    error = Signal(str)
    status = Signal(str)

    def __init__(self, language_code=None):
        super().__init__()
        self.language_code = language_code

    @staticmethod
    def _float_env(name: str, default: float, *, minimum: float = 0.0) -> float:
        """Read a positive numeric voice setting safely from the environment.

        Voice search must never fail merely because an optional .env setting is
        missing or malformed. Invalid, non-finite, or too-small values fall back
        to the known-safe default.
        """
        raw = os.getenv(name, "").strip()
        if not raw:
            return float(default)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return float(default)
        if not math.isfinite(value) or value < minimum:
            return float(default)
        return value

    @staticmethod
    def _rms_raw(raw: bytes) -> float:
        """Return RMS level for signed 16-bit mono PCM bytes."""
        if not raw:
            return 0.0
        # Ignore a dangling byte rather than letting array.frombytes() fail.
        usable = raw[: len(raw) - (len(raw) % 2)]
        if not usable:
            return 0.0
        samples = array("h")
        samples.frombytes(usable)
        if not samples:
            return 0.0
        return math.sqrt(sum(sample * sample for sample in samples) / len(samples))

    def _capture_audio(self, recognizer):
        """Capture one speech phrase from the configured/default microphone."""
        timeout = self._float_env("VOICE_LISTEN_TIMEOUT", 8.0)
        phrase_time_limit = self._float_env("VOICE_PHRASE_TIME_LIMIT", 15.0)
        calibration_duration = self._float_env("VOICE_AMBIENT_CALIBRATION", 0.6)

        device_raw = os.getenv("AUDIO_DEVICE_INDEX", "").strip()
        microphone_kwargs = {}
        sample_rate_raw = os.getenv("AUDIO_SAMPLE_RATE", "").strip()
        if sample_rate_raw:
            try:
                microphone_kwargs["sample_rate"] = int(sample_rate_raw)
            except ValueError:
                self.status.emit(
                    f"Ignoring invalid AUDIO_SAMPLE_RATE={sample_rate_raw!r}; using device default."
                )
        if device_raw:
            try:
                microphone_kwargs["device_index"] = int(device_raw)
            except ValueError:
                self.status.emit(
                    f"Ignoring invalid AUDIO_DEVICE_INDEX={device_raw!r}; using default microphone."
                )

        microphone = sr.Microphone(**microphone_kwargs)
        self.status.emit("Calibrating microphone…")
        with microphone as source:
            # Dynamic threshold + a short ambient calibration is considerably
            # more reliable than using a hard-coded microphone threshold.
            recognizer.adjust_for_ambient_noise(source, duration=calibration_duration)
            recognizer.dynamic_energy_threshold = True
            recognizer.pause_threshold = 0.8
            recognizer.phrase_threshold = 0.2
            recognizer.non_speaking_duration = 0.4
            self.status.emit(
                f"Listening… speak now (energy threshold {recognizer.energy_threshold:.0f})"
            )
            return recognizer.listen(
                source,
                timeout=timeout,
                phrase_time_limit=phrase_time_limit,
            )

    def _provider_modes(self, provider):
        name = str(getattr(provider, "name", "")).strip().lower()
        if name == "sarvam":
            # Document fetching benefits most from English-normalized speech.
            # Saaras v4 supports translate/codemix/transcribe on the same endpoint.
            return ("translate", "codemix", "transcribe")
        return ("transcribe",)

    def _recognize_with_provider(self, provider, wav_path: Path):
        """Return (transcript, detected_language, provider_error)."""
        provider_name = str(getattr(provider, "name", "provider")).lower()
        if provider_name == "bhashini" and not self.language_code:
            return "", "", (
                "BHASHINI ASR needs a selected speech language. "
                "Choose a language from the Language menu and try again."
            )

        last_error = ""
        for mode in self._provider_modes(provider):
            self.status.emit(
                f"Recognizing speech with {provider_name.title()} ({mode})…"
            )
            try:
                response = provider.speech_to_text(
                    str(wav_path),
                    language_code=self.language_code or "unknown",
                    mode=mode,
                ) or {}
            except Exception as error:
                last_error = str(error)
                self.status.emit(
                    f"{provider_name.title()} voice recognition failed; trying fallback…"
                )
                break

            text = str(response.get("transcript") or "").strip()
            detected = str(
                response.get("language_code") or self.language_code or ""
            ).strip()
            if detected:
                self.language_detected.emit(detected)
            if text:
                return text, detected, ""

            last_error = (
                f"{provider_name.title()} returned an empty transcript for mode={mode}."
            )
            # For Sarvam, trying transcribe after codemix is useful. For other
            # providers _provider_modes() contains only one mode.

        return "", "", last_error

    def _recognize_with_google(self, recognizer, audio):
        """Basic network fallback; intentionally limited to the common app languages."""
        fallback_languages = []
        if self.language_code:
            fallback_languages.append(self.language_code)
        for language in ("en-IN", "hi-IN"):
            if language not in fallback_languages:
                fallback_languages.append(language)

        for language in fallback_languages:
            self.status.emit(f"Using fallback speech recognition ({language})…")
            try:
                text = recognizer.recognize_google(audio, language=language).strip()
                if text:
                    self.language_detected.emit(language)
                    return text, ""
            except sr.UnknownValueError:
                continue
            except sr.RequestError as error:
                return "", (
                    "Fallback speech recognition is unavailable. "
                    f"Network/service error: {error}"
                )

        return "", "I could not understand your speech. Please try again."

    def run(self):
        if sr is None:
            self.error.emit(
                "Voice search needs SpeechRecognition and PyAudio. "
                "Install the project's requirements and try again."
            )
            return

        recognizer = sr.Recognizer()
        provider = None
        provider_error = ""

        try:
            # FIX: capture the microphone clip before any reference to ``audio``.
            audio = self._capture_audio(recognizer)

            raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
            rms = self._rms_raw(raw)
            duration = len(raw) / (16000 * 2) if raw else 0.0
            noise_gate = self._float_env("VOICE_MIN_RMS", 8.0, minimum=0.0)

            if not raw or duration < 0.08:
                self.error.emit(
                    "No usable microphone audio was captured. "
                    "Check your Windows input device and microphone permissions."
                )
                return

            # Do not reject quiet speakers with an aggressive hard-coded threshold.
            # Very low RMS is a useful warning, but SpeechRecognition/provider logic
            # should get the first chance to interpret the clip.
            if rms < noise_gate:
                self.error.emit(
                    "The microphone clip is almost silent "
                    f"(RMS={rms:.1f}, duration={duration:.2f}s). "
                    "Select the correct Windows microphone and speak closer to it."
                )
                return

            self.status.emit(
                f"Captured {duration:.1f}s of audio (RMS {rms:.0f}); processing…"
            )

            try:
                provider = build_provider()
            except Exception as error:
                provider_error = str(error)
                self.status.emit(
                    "Language provider unavailable; using fallback recognition…"
                )

            # Convert exactly once to a standard 16 kHz / 16-bit mono WAV for
            # remote STT providers. The file is removed immediately after use.
            temp_path = None
            try:
                if provider is not None:
                    with tempfile.NamedTemporaryFile(
                        suffix=".wav", delete=False
                    ) as temp:
                        temp_path = Path(temp.name)
                        temp.write(
                            audio.get_wav_data(
                                convert_rate=16000,
                                convert_width=2,
                            )
                        )

                    text, detected, remote_error = self._recognize_with_provider(
                        provider, temp_path
                    )
                    if text:
                        self.finished.emit(text)
                        return
                    if remote_error:
                        provider_error = remote_error

                # Remote STT failed/unavailable. Keep voice search usable for common
                # English/Hindi cases instead of forcing the user to type the query.
                self.status.emit("Using fallback speech recognition…")
                text, fallback_error = self._recognize_with_google(
                    recognizer, audio
                )
                if text:
                    self.finished.emit(text)
                    return

                if provider_error:
                    self.error.emit(
                        f"Voice recognition failed after microphone capture. "
                        f"Provider: {provider_error} "
                        f"Fallback: {fallback_error} "
                        "Check your API key/network or select the correct microphone."
                    )
                else:
                    self.error.emit(fallback_error)
            finally:
                if temp_path is not None:
                    temp_path.unlink(missing_ok=True)

        except sr.WaitTimeoutError:
            self.error.emit(
                "No speech started before the listening timeout. "
                "Click the microphone and speak clearly."
            )
        except OSError as error:
            self.error.emit(
                "Microphone could not be accessed. "
                f"{error} Check Windows microphone permissions and PyAudio installation."
            )
        except Exception as error:
            self.error.emit(f"Voice input failed: {error}")


class VoiceAssistant(QObject):
    text_received = Signal(str)
    language_detected = Signal(str)
    status_changed = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, parent=None, language_code=None):
        super().__init__(parent)
        self.thread = None
        self.worker = None
        self.language_code = language_code

    def set_language_code(self, language_code):
        self.language_code = language_code

    def start(self):
        if self.thread is not None and self.thread.isRunning():
            return
        self.thread = QThread()
        self.worker = VoiceWorker(self.language_code)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.status.connect(self.status_changed.emit)
        self.worker.finished.connect(self._handle_finished)
        self.worker.language_detected.connect(self.language_detected.emit)
        self.worker.error.connect(self._handle_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.error.connect(self.thread.quit)
        self.thread.finished.connect(self._cleanup)
        self.thread.start()

    def _handle_finished(self, text: str):
        self.text_received.emit(text)

    def _handle_error(self, message: str):
        self.error_occurred.emit(message)

    def _cleanup(self):
        if self.worker is not None:
            self.worker.deleteLater()
        if self.thread is not None:
            self.thread.deleteLater()
        self.worker = None
        self.thread = None
