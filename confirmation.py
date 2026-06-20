YES_WORDS = {
    "y",
    "yes",
    "evet",
    "e",
    "tamam",
    "onay",
    "onayla",
    "confirm",
    "ok",
    "okay",
}

NO_WORDS = {
    "n",
    "no",
    "hayir",
    "hayır",
    "iptal",
    "cancel",
    "reject",
    "vazgec",
    "vazgeç",
}


def normalize_confirm_response(line: str) -> str | None:
    text = (line or "").strip().lower()
    if not text:
        return None
    if text in YES_WORDS:
        return "y"
    if text in NO_WORDS:
        return "n"
    return None
