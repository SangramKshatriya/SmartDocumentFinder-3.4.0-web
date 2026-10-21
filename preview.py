"""Compatibility helpers for older integrations."""
from content_extractor import extract_text


def get_preview_text(file_path: str) -> str:
    return extract_text(file_path)
