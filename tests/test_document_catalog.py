from document_catalog import aliases_for, display_name, iter_aliases


def test_catalog_aliases_and_display_name():
    assert "pan card" in aliases_for("pan")
    assert display_name("pan") == "PAN Card"
    assert display_name("unknown_type") == "Unknown Type"


def test_iter_aliases_contains_canonical_documents():
    aliases = dict(iter_aliases())
    assert aliases["aadhaar"] == "aadhaar"
    assert aliases["pan card"] == "pan"
