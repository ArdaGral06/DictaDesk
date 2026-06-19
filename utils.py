import re


def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


_TR_FOLD_TABLE = str.maketrans(
    {
        "ç": "c",
        "ğ": "g",
        "ı": "i",
        "ö": "o",
        "ş": "s",
        "ü": "u",
        "Ç": "c",
        "Ğ": "g",
        "İ": "i",
        "Ö": "o",
        "Ş": "s",
        "Ü": "u",
    }
)


def fold_text(text: str) -> str:
    return text.translate(_TR_FOLD_TABLE).lower()


def extract_tail_text(full_text: str, phrase: str) -> str:
    if not full_text or not phrase:
        return ""

    phrase_words = [
        m.group(0).lower() for m in re.finditer(r"\w+", phrase, flags=re.UNICODE)
    ]
    if not phrase_words:
        return ""

    word_spans = [
        (m.group(0), m.start(), m.end())
        for m in re.finditer(r"\w+", full_text, flags=re.UNICODE)
    ]
    if not word_spans:
        return ""

    words_lower = [w.lower() for w, _, _ in word_spans]
    limit = len(words_lower) - len(phrase_words) + 1
    for i in range(max(0, limit)):
        if words_lower[i : i + len(phrase_words)] == phrase_words:
            end_pos = word_spans[i + len(phrase_words) - 1][2]
            return full_text[end_pos:].strip()

    norm_text = normalize_text(full_text)
    norm_phrase = normalize_text(phrase)
    if norm_phrase:
        idx = norm_text.find(norm_phrase)
        if idx != -1:
            return norm_text[idx + len(norm_phrase) :].strip()

    return ""


def parse_int_from_text(text: str, lang: str) -> int | None:
    if not text:
        return None

    digits = re.findall(r"-?\d+", text)
    if digits:
        try:
            return int(digits[0])
        except Exception:
            pass

    tokens = re.findall(r"[A-Za-zçğıöşüÇĞİÖŞÜ]+", text)
    tokens = [fold_text(t) for t in tokens]
    if not tokens:
        return None

    if lang == "tr":
        return _parse_tr_number(tokens)
    return _parse_en_number(tokens)


def _parse_en_number(tokens: list[str]) -> int | None:
    units = {
        "zero": 0,
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "twelve": 12,
        "thirteen": 13,
        "fourteen": 14,
        "fifteen": 15,
        "sixteen": 16,
        "seventeen": 17,
        "eighteen": 18,
        "nineteen": 19,
    }
    tens = {
        "twenty": 20,
        "thirty": 30,
        "forty": 40,
        "fifty": 50,
        "sixty": 60,
        "seventy": 70,
        "eighty": 80,
        "ninety": 90,
    }

    current = 0
    started = False
    for tok in tokens:
        if tok == "and":
            if started:
                continue
            continue
        if tok in units:
            current += units[tok]
            started = True
            continue
        if tok in tens:
            current += tens[tok]
            started = True
            continue
        if tok == "hundred":
            current = 100 if not started else current * 100
            started = True
            continue
        if started:
            break

    return current if started else None


def _parse_tr_number(tokens: list[str]) -> int | None:
    units = {
        "sifir": 0,
        "bir": 1,
        "iki": 2,
        "uc": 3,
        "dort": 4,
        "bes": 5,
        "alti": 6,
        "yedi": 7,
        "sekiz": 8,
        "dokuz": 9,
    }
    tens = {
        "on": 10,
        "yirmi": 20,
        "otuz": 30,
        "kirk": 40,
        "elli": 50,
        "altmis": 60,
        "yetmis": 70,
        "seksen": 80,
        "doksan": 90,
    }

    current = 0
    started = False
    for tok in tokens:
        if tok in units:
            current += units[tok]
            started = True
            continue
        if tok in tens:
            current += tens[tok]
            started = True
            continue
        if tok == "yuz":
            current = 100 if not started else current * 100
            started = True
            continue
        if started:
            break

    return current if started else None
