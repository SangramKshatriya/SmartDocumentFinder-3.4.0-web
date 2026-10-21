"""Generic BHASHINI pipeline adapter.

BHASHINI exposes model/pipeline-specific service IDs.  This adapter intentionally
keeps those IDs in environment variables instead of hard-coding a pipeline that
may change. Use the BHASHINI developer portal to select pipelines and configure:

BHASHINI_API_KEY
BHASHINI_PIPELINE_URL
BHASHINI_TRANSLATION_SERVICE_ID
BHASHINI_ASR_SERVICE_ID
BHASHINI_TTS_SERVICE_ID
BHASHINI_LID_SERVICE_ID
BHASHINI_TRANSLITERATION_SERVICE_ID
"""

import base64
import os
from pathlib import Path
from typing import Dict, Optional

import requests

from services.base_provider import LanguageProvider


class BhashiniProvider(LanguageProvider):
    name = "bhashini"

    def __init__(self):
        self.api_key = os.getenv("BHASHINI_API_KEY", "").strip()
        self.pipeline_url = os.getenv(
            "BHASHINI_PIPELINE_URL",
            "https://dhruva-api.bhashini.gov.in/services/inference/pipeline",
        )
        if not self.api_key:
            raise ValueError("BHASHINI_API_KEY is not configured")

    def _compute(self, task: dict, input_data: dict):
        response = requests.post(
            self.pipeline_url,
            headers={
                "Authorization": self.api_key,
                "Content-Type": "application/json",
            },
            json={"pipelineTasks": [task], "inputData": input_data},
            timeout=60,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as error:
            raise RuntimeError(f"BHASHINI API {response.status_code}: {response.text[:500]}") from error
        return response.json()

    def _service(self, env_name: str) -> str:
        service_id = os.getenv(env_name, "").strip()
        if not service_id:
            raise RuntimeError(f"Configure {env_name} with a serviceId from BHASHINI pipeline discovery")
        return service_id

    def detect_language(self, text: str) -> Dict:
        service_id = self._service("BHASHINI_LID_SERVICE_ID")
        task = {
            "taskType": "lid",
            "config": {"serviceId": service_id},
        }
        response = self._compute(task, {"input": [{"source": text[:1000]}]})
        config = response.get("pipelineResponse", [{}])[0].get("output", [{}])[0]
        return {
            "language_code": config.get("langCode") or config.get("languageCode"),
            "script_code": config.get("scriptCode"),
            "confidence": config.get("confidence"),
        }

    def translate(self, text: str, source_language_code: str, target_language_code: str) -> str:
        service_id = self._service("BHASHINI_TRANSLATION_SERVICE_ID")
        task = {
            "taskType": "translation",
            "config": {
                "serviceId": service_id,
                "language": {
                    "sourceLanguage": source_language_code.split("-")[0],
                    "targetLanguage": target_language_code.split("-")[0],
                },
            },
        }
        response = self._compute(task, {"input": [{"source": text[:2000]}]})
        output = response.get("pipelineResponse", [{}])[0].get("output", [{}])[0]
        return output.get("target", "") or output.get("translatedText", "")

    def transliterate(self, text: str, source_language_code: str, target_language_code: str) -> str:
        service_id = self._service("BHASHINI_TRANSLITERATION_SERVICE_ID")
        task = {
            "taskType": "transliteration",
            "config": {
                "serviceId": service_id,
                "language": {
                    "sourceLanguage": source_language_code.split("-")[0],
                    "targetLanguage": target_language_code.split("-")[0],
                },
            },
        }
        response = self._compute(task, {"input": [{"source": text[:2000]}]})
        output = response.get("pipelineResponse", [{}])[0].get("output", [{}])[0]
        return output.get("target", "") or output.get("transliteratedText", "")

    def speech_to_text(self, audio_path: str, language_code: Optional[str] = None, mode: str = "transcribe") -> Dict:
        service_id = self._service("BHASHINI_ASR_SERVICE_ID")
        audio_b64 = base64.b64encode(Path(audio_path).read_bytes()).decode("ascii")
        task = {
            "taskType": "asr",
            "config": {
                "serviceId": service_id,
                "language": {"sourceLanguage": (language_code or "") .split("-")[0] if language_code else ""},
                "audioFormat": "wav",
                "samplingRate": 16000,
            },
        }
        response = self._compute(task, {"audio": [{"audioContent": audio_b64}]})
        output = response.get("pipelineResponse", [{}])[0].get("output", [{}])[0]
        return {"transcript": output.get("source", ""), "language_code": language_code}

    def text_to_speech(self, text: str, language_code: str, output_path: str) -> str:
        service_id = self._service("BHASHINI_TTS_SERVICE_ID")
        task = {
            "taskType": "tts",
            "config": {
                "serviceId": service_id,
                "language": {"sourceLanguage": language_code.split("-")[0]},
                "gender": os.getenv("BHASHINI_TTS_GENDER", "female"),
                "samplingRate": 22050,
            },
        }
        response = self._compute(task, {"input": [{"source": text[:2000]}]})
        output = response.get("pipelineResponse", [{}])[0].get("audio", [{}])[0]
        audio_b64 = output.get("audioContent", "")
        if not audio_b64:
            raise RuntimeError("BHASHINI TTS returned no audio")
        Path(output_path).write_bytes(base64.b64decode(audio_b64))
        return output_path
