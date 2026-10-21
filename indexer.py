import hashlib
from pathlib import Path
from typing import Callable, Optional

from content_extractor import extract_text
from database import (
    delete_documents_not_in_paths,
    get_document_by_path,
    upsert_document,
)
from query_processor import infer_document_type
from scanner import scan_folder


def file_hash(file_path: str, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(file_path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def detect_language(text: str) -> str:
    if not text:
        return ""
    ranges = [
        ("hi", 0x0900, 0x097F),
        ("bn", 0x0980, 0x09FF),
        ("gu", 0x0A80, 0x0AFF),
        ("pa", 0x0A00, 0x0A7F),
        ("or", 0x0B00, 0x0B7F),
        ("ta", 0x0B80, 0x0BFF),
        ("te", 0x0C00, 0x0C7F),
        ("kn", 0x0C80, 0x0CFF),
        ("ml", 0x0D00, 0x0D7F),
    ]
    scores = {name: 0 for name, _, _ in ranges}
    latin = 0
    for char in text:
        cp = ord(char)
        for name, start, end in ranges:
            if start <= cp <= end:
                scores[name] += 1
                break
        else:
            if char.isascii() and char.isalpha():
                latin += 1
    dominant = max(scores, key=scores.get) if scores else ""
    dominant_count = scores.get(dominant, 0)
    if dominant_count and latin and latin >= dominant_count * 0.25:
        return f"{dominant}+en"
    if dominant_count:
        return dominant
    if latin:
        return "en"
    return ""


def index_file(file_info: dict, force: bool = False):
    path = str(Path(file_info["path"]).resolve())
    existing = get_document_by_path(path)
    if (
        existing is not None
        and not force
        and int(existing["size"] or 0) == int(file_info["size"])
        and abs(float(existing["modified_time"] or 0) - float(file_info["modified_time"])) < 0.01
    ):
        return {"path": path, "changed": False, "error": ""}

    content = ""
    status = "ok"
    error_message = ""
    try:
        content = extract_text(path)
    except Exception as error:
        status = "error"
        error_message = str(error)

    try:
        digest = file_hash(path)
    except Exception:
        digest = ""

    document_type = infer_document_type(file_info["name"], content)
    language = detect_language(content)
    upsert_document(
        name=file_info["name"],
        path=path,
        extension=file_info["extension"],
        size=file_info["size"],
        modified_time=file_info["modified_time"],
        content=content,
        content_hash=digest,
        document_type=document_type or "",
        language=language,
        extraction_status=status,
        extraction_error=error_message,
    )
    return {"path": path, "changed": True, "error": error_message}


def index_folder(
    folder_path: str,
    force: bool = False,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> dict:
    files = scan_folder(folder_path)
    valid_paths = [item["path"] for item in files]
    # The app indexes one active root folder at a time; remove records from any
    # previous folder so stale documents cannot compete in search.
    deleted = delete_documents_not_in_paths(valid_paths)

    changed = 0
    skipped = 0
    errors = 0
    total = len(files)
    for index, file_info in enumerate(files, start=1):
        if should_stop and should_stop():
            break
        result = index_file(file_info, force=force)
        if result["changed"]:
            changed += 1
        else:
            skipped += 1
        if result["error"]:
            errors += 1
        if progress_callback:
            progress_callback(index, total, file_info["name"])

    return {
        "total": total,
        "changed": changed,
        "skipped": skipped,
        "deleted": deleted,
        "errors": errors,
    }
