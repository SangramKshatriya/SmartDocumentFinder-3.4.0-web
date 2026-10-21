from pathlib import Path
from typing import Dict, List

from config import RECURSIVE_SCAN, SUPPORTED_EXTENSIONS


def scan_folder(folder_path: str, recursive: bool = RECURSIVE_SCAN) -> List[Dict]:
    root = Path(folder_path).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Folder does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    iterator = root.rglob("*") if recursive else root.iterdir()
    files: List[Dict] = []
    for file_path in iterator:
        if not file_path.is_file() or file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        try:
            stat = file_path.stat()
        except (PermissionError, OSError):
            continue
        files.append({
            "name": file_path.name,
            "path": str(file_path),
            "extension": file_path.suffix.lower(),
            "size": stat.st_size,
            "modified_time": stat.st_mtime,
        })
    files.sort(key=lambda item: item["path"].lower())
    return files
