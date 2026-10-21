from abc import ABC, abstractmethod
from typing import Dict, Optional


class LanguageProvider(ABC):
    name = "provider"

    @abstractmethod
    def detect_language(self, text: str) -> Dict:
        raise NotImplementedError

    @abstractmethod
    def translate(self, text: str, source_language_code: str, target_language_code: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def transliterate(self, text: str, source_language_code: str, target_language_code: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def speech_to_text(
        self,
        audio_path: str,
        language_code: Optional[str] = None,
        mode: str = "transcribe",
    ) -> Dict:
        raise NotImplementedError

    @abstractmethod
    def text_to_speech(
        self,
        text: str,
        language_code: str,
        output_path: str,
    ) -> str:
        raise NotImplementedError
