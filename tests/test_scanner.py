from pathlib import Path
from scanner import scan_folder


def test_recursive_scanner(tmp_path: Path):
    (tmp_path / "nested").mkdir()
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "nested" / "b.txt").write_text("world")
    assert {item["name"] for item in scan_folder(str(tmp_path))} == {"a.txt", "b.txt"}
