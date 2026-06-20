import re

from utils import fold_text


def looks_like_url(value: str) -> bool:
    v = (value or "").strip().lower()
    return v.startswith(("http://", "https://", "www."))


def looks_like_path(value: str) -> bool:
    v = (value or "").strip()
    return "\\" in v or "/" in v or re.match(r"^[A-Za-z]:\\", v) is not None


def clean_youtube_query(text: str) -> str:
    raw = (text or "").lower()
    raw = re.sub(r"[\"'“”‘’.,!?;:()\[\]{}<>]", " ", raw)
    tokens = re.findall(r"[a-z0-9ığüşöç]+", raw, flags=re.IGNORECASE)
    stopwords = {
        "bana",
        "bir",
        "lütfen",
        "please",
        "the",
        "a",
        "an",
        "and",
        "or",
        "youtube",
        "youtubedan",
        "youtubeden",
        "youtube'dan",
        "yt",
        "video",
        "videosu",
        "videosunu",
        "videooo",
        "videoyu",
        "videolar",
        "izle",
        "izlemek",
        "watch",
        "play",
        "aç",
        "ac",
        "open",
        "ara",
        "arama",
        "aramasi",
        "bul",
        "playwright",
        "kullanma",
        "kullanmadan",
        "normal",
        "varsayilan",
        "varsayılan",
        "tarayici",
        "tarayıcı",
        "browser",
        "default",
    }
    cleaned = [tok for tok in tokens if tok and tok not in stopwords]
    return " ".join(cleaned).strip()


def detect_browser_request(text: str) -> tuple[bool, str | None]:
    phrase = fold_text(text or "")
    avoid_playwright = False
    if any(
        key in phrase
        for key in (
            "playwright kullanma",
            "playwright istemiyorum",
            "normal tarayici",
            "normal tarayıcı",
            "varsayilan tarayici",
            "varsayılan tarayıcı",
            "default browser",
            "normal browser",
            "no playwright",
            "without playwright",
        )
    ):
        avoid_playwright = True
    browser = None
    for name in ("chrome", "edge", "brave", "firefox", "opera"):
        if name in phrase:
            browser = name
            break
    if browser:
        avoid_playwright = True
    return avoid_playwright, browser


_DISCORD_BAD_NAMES = frozenset(
    {
        "discord",
        "uygulama",
        "uygulamada",
        "application",
        "app",
        "adli",
        "adlı",
        "bul",
        "find",
    }
)


def _clean_discord_name(name: str) -> str:
    name = (name or "").strip(" :,.")
    name = re.sub(r"\s+(?:bul|ve|and|icin|için)$", "", name, flags=re.I).strip()
    if re.search(r"uygulamada\s+", name, flags=re.I):
        name = re.sub(r"^.+?uygulamada\s+", "", name, flags=re.I).strip()
    if name.lower().startswith("discord "):
        name = name[8:].strip()
    return name


def extract_discord_server_name(text: str) -> str | None:
    if not text:
        return None
    candidates: list[str] = []
    for pat in (
        r"uygulamada\s+(.+?)\s+server(?:i(?:ni|na|nda|ndaki)?)?\b",
        r"uygulamada\s+(.+?)\s+sunucu(?:su(?:ndaki|nda|sunda)?)?\b",
        r"(?:server|sunucu)\s+(?:ad[ıi]\s+)?(.+?)(?:\s+(?:kanal|channel)\b)",
    ):
        match = re.search(pat, text, flags=re.IGNORECASE)
        if match:
            candidates.append(_clean_discord_name(match.group(1)))
    for match in re.finditer(
        r"([\w][\w\s.-]{1,48}?)\s+server(?:i(?:ni|na|nda|ndaki)?)?\b",
        text,
        flags=re.IGNORECASE,
    ):
        candidates.append(_clean_discord_name(match.group(1)))
    for match in re.finditer(
        r"([\w][\w\s.-]{1,48}?)\s+sunucu(?:su(?:ndaki|nda|sunda)?)?\b",
        text,
        flags=re.IGNORECASE,
    ):
        candidates.append(_clean_discord_name(match.group(1)))
    seen: set[str] = set()
    for name in candidates:
        folded = fold_text(name)
        if not name or folded in _DISCORD_BAD_NAMES or folded in seen:
            continue
        seen.add(folded)
        return name
    return None


def extract_discord_channel_name(text: str) -> str | None:
    if not text:
        return None
    patterns = (
        r"([\w#.-]+)\s+kanal(?:i(?:na|ni|a|sina|sına))?",
        r"(?:kanal|channel)\s+(?:ad[ıi]\s+)?(?:#)?([\w.-]+)",
        r"#([\w.-]+)",
    )
    for pat in patterns:
        match = re.search(pat, text, flags=re.IGNORECASE)
        if not match:
            continue
        name = match.group(1).strip().lstrip("#")
        if name and fold_text(name) not in _DISCORD_BAD_NAMES:
            return name
    return None


def extract_discord_message(text: str) -> str | None:
    if not text:
        return None
    for pattern in (r'"([^"]+)"', r"'([^']+)'"):
        matches = re.findall(pattern, text)
        if matches:
            return matches[-1].strip()
    tail = re.search(
        r"kanal(?:ına|ina|a)?\s+(.+?)$",
        text,
        flags=re.IGNORECASE,
    )
    if tail:
        msg = tail.group(1).strip(" :,.")
        msg = re.sub(
            r"\s+(?:yaz|gonder|gönder|send)$",
            "",
            msg,
            flags=re.IGNORECASE,
        ).strip(" :,.")
        if msg and not re.search(r"\bkanal\b", msg, flags=re.I):
            return msg
    msg_match = re.search(
        r"(?:mesaj(?:ı|i)?|yaz|gonder|gönder|send)\s+(?:olarak\s+)?(.+?)$",
        text,
        flags=re.IGNORECASE,
    )
    if msg_match:
        msg = msg_match.group(1).strip(" :,.")
        msg = re.sub(r"^(?:mesaj(?:ı|i)?\s+)", "", msg, flags=re.I).strip(" :,.")
        msg = re.sub(
            r"\s+(?:mesaj(?:ı|i)?\s+)?(?:yaz|gonder|gönder|send)$",
            "",
            msg,
            flags=re.I,
        ).strip(" :,.")
        return msg or None
    return None


def parse_discord_channel_request(text: str) -> tuple[str, str, str] | None:
    """Parse 'Discord server X channel Y send message Z' style commands."""
    folded = fold_text(text or "")
    if "discord" not in folded:
        return None
    has_server_hint = any(w in folded for w in ("sunucu", "server"))
    has_channel_hint = any(
        w in folded for w in ("kanal", "channel", "genel", "general", "#", "sohbet")
    )
    if not has_server_hint and not has_channel_hint:
        return None
    if not any(
        w in folded
        for w in ("mesaj", "message", "yaz", "gonder", "send", "git", "gec", "open")
    ):
        return None

    server = extract_discord_server_name(text)
    channel = extract_discord_channel_name(text)
    msg = extract_discord_message(text)

    if not server and not channel:
        return None
    if not msg and not any(w in folded for w in ("git", "gec", "open")):
        return None
    return (server or "", channel or "", msg or "")
