import base64
import json
import os
import time
from pathlib import Path
from typing import Dict, Optional

import requests
from dotenv import load_dotenv

# Make provider configuration reliable even when this module is constructed
# outside app.py (for example from the voice worker or a standalone script).
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=False)

from services.base_provider import LanguageProvider


class SarvamProvider(LanguageProvider):
    name = "sarvam"
    BASE_URL = "https://api.sarvam.ai"

    def __init__(
        self,
        api_key: Optional[str] = None,
        translation_model: Optional[str] = None,
        auto_translation_model: Optional[str] = None,
        stt_model: Optional[str] = None,
        tts_model: Optional[str] = None,
        timeout: int = 45,
    ):
        raw_key = api_key if api_key is not None else os.getenv("SARVAM_API_KEY", "")
        # Accept keys copied from .env as either plain values or quoted values.
        self.api_key = str(raw_key).strip().strip("\'").strip('"')
        self.translation_model = translation_model or os.getenv(
            "SARVAM_TRANSLATION_MODEL", "sarvam-translate:v1"
        )
        self.auto_translation_model = auto_translation_model or os.getenv(
            "SARVAM_AUTO_TRANSLATION_MODEL", "mayura:v1"
        )
        self.stt_model = stt_model or os.getenv("SARVAM_STT_MODEL", "saaras:v4")
        self.tts_model = tts_model or os.getenv("SARVAM_TTS_MODEL", "bulbul:v3")
        self.timeout = timeout
        self.session = requests.Session()
        if not self.api_key:
            raise ValueError("SARVAM_API_KEY is not configured")

    def _request(self, method: str, path: str, **kwargs):
        headers = kwargs.pop("headers", {})
        headers["API-Subscription-Key"] = self.api_key
        last_error = None
        for attempt in range(3):
            try:
                response = self.session.request(
                    method,
                    f"{self.BASE_URL}{path}",
                    headers=headers,
                    timeout=self.timeout,
                    **kwargs,
                )
                if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                    time.sleep(0.8 * (2 ** attempt))
                    continue
                try:
                    response.raise_for_status()
                except requests.HTTPError as error:
                    detail = response.text[:800]
                    raise RuntimeError(f"Sarvam API {response.status_code}: {detail}") from error
                return response
            except (requests.Timeout, requests.ConnectionError) as error:
                last_error = error
                if attempt < 2:
                    time.sleep(0.8 * (2 ** attempt))
                    continue
                raise RuntimeError(f"Sarvam network error: {error}") from error
        raise RuntimeError(f"Sarvam request failed: {last_error}")

    def detect_language(self, text: str) -> Dict:
        response = self._request("POST", "/text-lid", json={"input": text[:1000]}).json()
        return {
            "language_code": response.get("language_code"),
            "script_code": response.get("script_code"),
            "confidence": response.get("confidence"),
        }

    def translate(self, text: str, source_language_code: str, target_language_code: str) -> str:
        if len(text) > 2000:
            raise ValueError("Sarvam text translation accepts at most 2000 characters per request")
        payload = {
            "input": text,
            "source_language_code": source_language_code,
            "target_language_code": target_language_code,
            "model": self.translation_model,
            "mode": os.getenv("SARVAM_TRANSLATION_MODE", "formal"),
            "numerals_format": os.getenv("SARVAM_NUMERALS_FORMAT", "international"),
        }
        response = self._request("POST", "/translate", json=payload).json()
        return response.get("translated_text", "")

    def translate_auto(self, text: str, target_language_code: str = "en-IN") -> str:
        """Sarvam Mayura auto-detect path, useful for Romanized/code-mixed queries."""
        if len(text) > 1000:
            text = text[:1000]
        payload = {
            "input": text,
            "source_language_code": "auto",
            "target_language_code": target_language_code,
            "model": self.auto_translation_model,
            "mode": os.getenv("SARVAM_TRANSLATION_MODE", "modern-colloquial"),
            "numerals_format": os.getenv("SARVAM_NUMERALS_FORMAT", "international"),
        }
        response = self._request("POST", "/translate", json=payload).json()
        return response.get("translated_text", "")

    def transliterate(self, text: str, source_language_code: str, target_language_code: str) -> str:
        payload = {
            "input": text[:2000],
            "source_language_code": source_language_code,
            "target_language_code": target_language_code,
        }
        response = self._request("POST", "/transliterate", json=payload).json()
        return response.get("transliterated_text", "")

    def speech_to_text(
        self,
        audio_path: str,
        language_code: Optional[str] = None,
        mode: str = "codemix",
    ) -> Dict:
        normalized_mode = str(mode or "transcribe").strip().lower()
        allowed_modes = {"transcribe", "translate", "verbatim", "translit", "codemix"}
        if normalized_mode not in allowed_modes:
            raise ValueError(
                f"Unsupported Sarvam speech mode {normalized_mode!r}; "
                f"choose one of {sorted(allowed_modes)}"
            )

        data = {
            "model": self.stt_model,
            "mode": normalized_mode,
            # "unknown" asks Saaras to detect the spoken language. When a
            # language is explicitly selected, detection is skipped by Sarvam.
            "language_code": (language_code or "unknown").strip() or "unknown",
        }

        # Keyterm prompting is supported by Saaras v4. Do not send this field
        # when a caller intentionally chooses an older model.
        if str(self.stt_model).strip().lower() == "saaras:v4":
            keyterms_raw = os.getenv("SARVAM_KEYTERMS", "").strip()
            if keyterms_raw:
                keyterms = [term.strip() for term in keyterms_raw.split(",") if term.strip()]
            else:
                # Bias Saaras toward the document names this application is
                # designed to retrieve. Users often speak these names in
                # mixed Indic/English.
                keyterms = [
                    "Aadhaar", "PAN card", "10th marksheet", "12th marksheet",
                    "caste certificate", "fee receipt", "income certificate",
                    "passbook", "affidavit", "semester", "voter card", "voter ID",
                    "driving licence", "registration certificate", "insurance",
                ]
            data["keyterms"] = json.dumps(keyterms[:50], ensure_ascii=False)
        audio = Path(audio_path)
        if not audio.is_file():
            raise FileNotFoundError(f"Audio file not found: {audio}")

        with audio.open("rb") as handle:
            response = self._request(
                "POST",
                "/speech-to-text",
                files={"file": (audio.name, handle, "audio/wav")},
                data=data,
            ).json()

        transcript = str(response.get("transcript") or "").strip()
        return {
            "transcript": transcript,
            "language_code": response.get("language_code"),
            "language_probability": response.get("language_probability"),
        }

    def text_to_speech(self, text: str, language_code: str, output_path: str) -> str:
        payload = {
            "text": text[:2500],
            "model": self.tts_model,
            "language_code": language_code,
            "speaker": os.getenv("SARVAM_TTS_SPEAKER", "shubh"),
        }
        response = self._request("POST", "/text-to-speech", json=payload).json()
        audios = response.get("audios") or []
        if not audios:
            raise RuntimeError("Sarvam TTS returned no audio")
        audio_bytes = base64.b64decode(audios[0])
        Path(output_path).write_bytes(audio_bytes)
        return output_path
