from action_parsers import (
    clean_youtube_query,
    detect_browser_request,
    extract_discord_channel_name,
    extract_discord_server_name,
    looks_like_url,
    parse_discord_channel_request,
)


def test_clean_youtube_query():
    q = clean_youtube_query("youtube ac lütfen funny cat video izle")
    assert "youtube" not in q.split()
    assert "cat" in q


def test_detect_browser_request():
    avoid, browser = detect_browser_request("chrome ile youtube ac")
    assert avoid is True
    assert browser == "chrome"


def test_looks_like_url():
    assert looks_like_url("https://example.com")
    assert not looks_like_url("notepad")


def test_discord_server_channel_parse():
    text = (
        'discord adlı uygulamada LoX eFootball serverını bul ve '
        'genel-sohbet kanalına "test" mesajı gönder'
    )
    parsed = parse_discord_channel_request(text)
    assert parsed == ("LoX eFootball", "genel-sohbet", "test")
    assert extract_discord_server_name(text) == "LoX eFootball"
    assert extract_discord_channel_name(text) == "genel-sohbet"
