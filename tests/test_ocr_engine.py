from PIL import Image

import ocr_engine


def test_choose_ocr_language_filters_to_installed_languages(monkeypatch):
    monkeypatch.setattr(ocr_engine, "_available_languages", lambda: {"eng", "hin"})
    monkeypatch.setattr(ocr_engine, "OCR_LANGUAGES", "eng+hin+mar")
    assert ocr_engine.choose_ocr_language() == "eng+hin"


def test_run_ocr_uses_fallback_psm_when_first_result_is_short(monkeypatch):
    calls = []
    monkeypatch.setattr(ocr_engine, "choose_ocr_language", lambda: "eng")

    def fake_ocr(image, lang, config):
        calls.append(config)
        return "short" if config.endswith("6") else "This is sufficiently long OCR text."

    monkeypatch.setattr(ocr_engine.pytesseract, "image_to_string", fake_ocr)
    result = ocr_engine.run_ocr(Image.new("RGB", (20, 20)))
    assert "sufficiently long" in result
    assert calls == ["--oem 3 --psm 6", "--oem 3 --psm 11"]


def test_extract_ocr_text_returns_empty_for_unsupported_extension(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("hello", encoding="utf-8")
    assert ocr_engine.extract_ocr_text(str(path)) == ""
