from dataclasses import dataclass
from typing import Optional

from language.detector import detect_language_local, guess_language_from_hints, normalize_bcp47
from services.base_provider import LanguageProvider
from query_processor import canonical_document_query, detect_document_type, extract_constraints


@dataclass(frozen=True)
class PreparedQuery:
    original: str
    language_code: Optional[str]
    script_code: Optional[str]
    confidence: float
    canonical_english: str
    document_type: Optional[str] = None
    document_name: str = ""
    transliterated: str = ""
    provider_used: str = "local"
    translation_ok: bool = False
    provider_error: str = ""


class LanguageManager:
    """Single canonical pipeline for search: detect -> translate -> extract document name."""

    def __init__(self, provider: Optional[LanguageProvider] = None):
        self.provider = provider

    @property
    def provider_name(self) -> str:
        return self.provider.name if self.provider else "local"

    def _local_document_fallback(self, original: str) -> str:
        document_type = detect_document_type(original)
        if not document_type:
            return ""
        return canonical_document_query(document_type, extract_constraints(original))

    def _translate(self, text: str, source_language_code: str, auto_detect: bool = False) -> tuple[str, str, str]:
        if not self.provider:
            return "", "local", "No remote language provider configured"
        if source_language_code == "en-IN":
            return text, self.provider.name, ""

        # Sarvam Mayura supports automatic source detection and is useful for
        # Romanized/code-mixed input where the exact Indic language is unclear.
        if getattr(self.provider, "name", "") == "sarvam" and (auto_detect or not source_language_code):
            translated = self.provider.translate_auto(text, target_language_code="en-IN").strip()
            if not translated:
                raise RuntimeError("Sarvam returned an empty automatic translation")
            return translated, self.provider.name, ""

        if not source_language_code:
            return "", self.provider.name, "Language code unavailable for exact translation"

        translated = self.provider.translate(
            text,
            source_language_code=source_language_code,
            target_language_code="en-IN",
        ).strip()
        if not translated:
            raise RuntimeError(f"{self.provider.name} returned an empty translation")
        return translated, self.provider.name, ""

    def prepare_query(self, text: str, preferred_language: Optional[str] = None) -> PreparedQuery:
        original = str(text or "").strip()
        if not original:
            return PreparedQuery("", preferred_language, None, 0.0, "")

        local_code, script_code, local_confidence = detect_language_local(original)
        hinted_code, hint_confidence = guess_language_from_hints(original)
        language_code = normalize_bcp47(preferred_language) or normalize_bcp47(hinted_code) or normalize_bcp47(local_code)
        confidence = max(float(local_confidence or 0.0), float(hint_confidence or 0.0))
        provider_error = ""

        # Provider LID is authoritative when Auto Detect is selected. The current
        # Sarvam LID endpoint exposes a narrower set than its translation model,
        # so a null/unsupported result falls back to our local candidates.
        if self.provider and not preferred_language:
            try:
                detected = self.provider.detect_language(original)
                detected_code = normalize_bcp47(detected.get("language_code"))
                # Sarvam LID currently reports Latin-script Romanized queries as
                # English in some cases. Preserve a stronger local/lexical hint
                # (e.g. "mujhe", "dikhao") instead of routing that text as English.
                if detected_code and not (detected_code == "en-IN" and hinted_code and hinted_code != "en-IN"):
                    language_code = detected_code
                script_code = detected.get("script_code") or script_code
                confidence = max(confidence, float(detected.get("confidence") or 0.0))
            except Exception as error:
                provider_error = f"Language detection failed: {error}"

        translated = ""
        provider_used = "local"
        translation_ok = False
        if language_code == "en-IN":
            translated = original
            translation_ok = True
            provider_used = self.provider.name if self.provider else "local"
        elif self.provider:
            try:
                # If auto-detection did not identify a language, let Sarvam Mayura
                # perform source detection. Otherwise use the exact language code.
                source_for_translation = language_code or ""
                romanized_hint = bool(script_code == "Latn" and hinted_code and hinted_code != "en-IN")
                translated, provider_used, translation_error = self._translate(
                    original, source_for_translation, auto_detect=romanized_hint
                )
                if translation_error and not translated:
                    provider_error = provider_error or translation_error
                translation_ok = bool(translated)
            except Exception as error:
                provider_error = f"Translation failed: {error}"
                provider_used = self.provider.name

        fallback_document = self._local_document_fallback(original)
        canonical_document = detect_document_type(translated) if translated else None
        canonical_constraints = extract_constraints(translated) if translated else extract_constraints(original)
        document_type = canonical_document or detect_document_type(original)
        document_name = canonical_document_query(document_type, canonical_constraints)

        if document_name:
            # Search is intentionally restricted to the document name after translation;
            # request filler like “please show my” never reaches the retriever.
            canonical_english = document_name
        elif translated:
            canonical_english = translated
        elif fallback_document:
            canonical_english = fallback_document
            document_type = detect_document_type(original)
            document_name = fallback_document
        else:
            canonical_english = original

        return PreparedQuery(
            original=original,
            language_code=language_code,
            script_code=script_code,
            confidence=confidence,
            canonical_english=canonical_english,
            document_type=document_type,
            document_name=document_name,
            provider_used=provider_used,
            translation_ok=translation_ok,
            provider_error=provider_error,
        )
