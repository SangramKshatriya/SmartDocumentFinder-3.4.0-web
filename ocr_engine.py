from pathlib import Path

import cv2
import numpy as np
import pymupdf
import pytesseract
from PIL import Image

from config import OCR_DPI, OCR_LANGUAGES, TESSERACT_DEFAULT_PATH

if Path(TESSERACT_DEFAULT_PATH).exists():
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_DEFAULT_PATH


def _available_languages():
    try:
        return set(pytesseract.get_languages(config=""))
    except Exception:
        return set()


def choose_ocr_language() -> str:
    configured = [item for item in OCR_LANGUAGES.replace(" ", "").split("+") if item]
    available = _available_languages()
    if not available:
        return "+".join(configured) or "eng"
    selected = [item for item in configured if item in available]
    if "eng" in available and "eng" not in selected:
        selected.insert(0, "eng")
    return "+".join(selected) or "eng"


def preprocess_for_ocr(pil_image: Image.Image) -> Image.Image:
    image = np.array(pil_image.convert("RGB"))
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    gray = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
    threshold = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11
    )
    threshold = cv2.resize(threshold, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    return Image.fromarray(threshold)


def run_ocr(image: Image.Image) -> str:
    language = choose_ocr_language()
    try:
        text = pytesseract.image_to_string(
            image,
            lang=language,
            config="--oem 3 --psm 6",
        ).strip()
    except Exception as error:
        raise RuntimeError(f"Tesseract OCR failed: {error}") from error
    if len(text) < 25:
        try:
            fallback = pytesseract.image_to_string(
                image,
                lang=language,
                config="--oem 3 --psm 11",
            ).strip()
            if len(fallback) > len(text):
                text = fallback
        except Exception:
            pass
    return text


def extract_image_text(file_path: str) -> str:
    with Image.open(file_path) as image:
        return run_ocr(preprocess_for_ocr(image))


def extract_scanned_pdf_text(file_path: str, skip_pages_with_text: bool = False) -> str:
    parts = []
    with pymupdf.open(file_path) as document:
        for page_number, page in enumerate(document, start=1):
            if skip_pages_with_text and len(page.get_text("text").strip()) >= 30:
                continue
            scale = OCR_DPI / 72.0
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            text = run_ocr(preprocess_for_ocr(image))
            if text:
                parts.append(f"[OCR Page {page_number}]\n{text}")
    return "\n\n".join(parts).strip()


def extract_ocr_text(file_path: str) -> str:
    extension = Path(file_path).suffix.lower()
    if extension in {".jpg", ".jpeg", ".png"}:
        return extract_image_text(file_path)
    if extension == ".pdf":
        return extract_scanned_pdf_text(file_path)
    return ""
