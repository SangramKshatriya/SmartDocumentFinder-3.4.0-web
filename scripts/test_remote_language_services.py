import os
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from services.provider_factory import build_provider

provider = build_provider()
if provider is None:
    raise SystemExit("No remote language provider configured. Set LANGUAGE_PROVIDER and its API key in .env.")

print(f"Provider: {provider.name}")
print("Language detection:", provider.detect_language("मेरा पैन कार्ड दिखाओ"))
print("Translation:", provider.translate("मेरा पैन कार्ड दिखाओ", "hi-IN", "en-IN"))
print("Transliteration:", provider.transliterate("मेरा पैन कार्ड", "hi-IN", "en-IN"))

try:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp:
        wav_path = temp.name
    provider.text_to_speech("आपकी पैन कार्ड फ़ाइल मिल गई है।", "hi-IN", wav_path)
    print(f"TTS saved: {wav_path}")
finally:
    if 'wav_path' in locals():
        Path(wav_path).unlink(missing_ok=True)
