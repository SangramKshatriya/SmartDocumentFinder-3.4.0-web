import os
from typing import Optional

from services.base_provider import LanguageProvider


def build_provider() -> Optional[LanguageProvider]:
    provider = os.getenv("LANGUAGE_PROVIDER", "sarvam").strip().lower()
    if provider in {"", "none", "local", "offline"}:
        return None
    if provider == "sarvam":
        if not os.getenv("SARVAM_API_KEY", "").strip():
            return None
        from services.sarvam_provider import SarvamProvider

        return SarvamProvider()
    if provider == "bhashini":
        if not os.getenv("BHASHINI_API_KEY", "").strip():
            return None
        from services.bhashini_provider import BhashiniProvider

        return BhashiniProvider()
    raise ValueError(f"Unsupported LANGUAGE_PROVIDER: {provider}")
