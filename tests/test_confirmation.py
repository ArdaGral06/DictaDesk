from confirmation import normalize_confirm_response


def test_yes_words():
    assert normalize_confirm_response("evet") == "y"
    assert normalize_confirm_response("YES") == "y"
    assert normalize_confirm_response("tamam") == "y"


def test_no_words():
    assert normalize_confirm_response("hayir") == "n"
    assert normalize_confirm_response("iptal") == "n"


def test_invalid():
    assert normalize_confirm_response("maybe") is None
