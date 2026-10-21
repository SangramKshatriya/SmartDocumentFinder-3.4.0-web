from preview import get_preview_text


def test_preview_text_for_text_file(tmp_path):
    path = tmp_path / "preview.txt"
    path.write_text("preview content", encoding="utf-8")
    assert get_preview_text(str(path)) == "preview content"
