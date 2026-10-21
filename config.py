from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("SMARTDOCUMENT_DATA_DIR", str(BASE_DIR / "data"))).expanduser().resolve()
DATABASE_PATH = DATA_DIR / "documents.db"

SUPPORTED_EXTENSIONS = {
    ".pdf", ".jpg", ".jpeg", ".png", ".docx", ".xlsx", ".xls", ".txt", ".xml"
}

DEFAULT_SEARCH_RESULT_LIMIT = 5
RECURSIVE_SCAN = True

# OCR: can be overridden with environment variables.
TESSERACT_DEFAULT_PATH = os.getenv(
    "TESSERACT_CMD",
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
)
OCR_LANGUAGES = os.getenv(
    "OCR_LANGUAGES",
    "eng+hin+mar+guj+tam+tel+kan+mal+ben+pan+ori+asm",
)
OCR_DPI = int(os.getenv("OCR_DPI", "220"))

APP_VERSION = "3.3.3"
DEFAULT_UI_LANGUAGE = os.getenv("DEFAULT_UI_LANGUAGE", "en-IN")
LANGUAGE_PROVIDER = os.getenv("LANGUAGE_PROVIDER", "sarvam")
