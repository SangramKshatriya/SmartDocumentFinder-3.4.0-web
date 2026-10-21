from query_processor import detect_document_type, extract_constraints, normalize_text, parse_query


def test_unicode_is_preserved():
    assert "पैन" in normalize_text("मेरा पैन कार्ड")
    assert "pan" in parse_query("मेरा पैन कार्ड दिखाओ").search_terms


def test_12th_constraint_is_preserved():
    intent = parse_query("show my 12th marksheet")
    assert intent.document_type == "marksheet"
    assert intent.constraints["grade"] == "12"
    assert "12th" in intent.search_terms


def test_vehicle_registration_does_not_match_card_substring():
    assert detect_document_type("show vehicle registration") == "rc"


def test_hindi_pan():
    assert detect_document_type("मेरा पैन कार्ड दिखाओ") == "pan"


def test_camelcase_filename_inference():
    from query_processor import infer_document_type
    assert infer_document_type("12thMarksheet.pdf") == "marksheet"
