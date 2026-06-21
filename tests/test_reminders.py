import sys
from datetime import datetime, timedelta

import pytest

from reminders import parse_reminder, schedule_reminder

NOW = datetime(2026, 6, 21, 12, 0, 0)


def test_parse_relative_minutes():
    target, msg = parse_reminder("+10m -> mola", now=NOW)
    assert target == NOW + timedelta(minutes=10)
    assert msg == "mola"


def test_parse_relative_bare_number_is_minutes():
    target, _ = parse_reminder("+30 -> x", now=NOW)
    assert target == NOW + timedelta(minutes=30)


def test_parse_relative_hours():
    target, _ = parse_reminder("+2h -> y", now=NOW)
    assert target == NOW + timedelta(hours=2)


def test_parse_absolute():
    target, msg = parse_reminder("2030-01-01 09:00 -> yeni yil", now=NOW)
    assert target == datetime(2030, 1, 1, 9, 0)
    assert msg == "yeni yil"


def test_parse_turkish_relative():
    target, msg = parse_reminder("5 dakika sonra -> ara", now=NOW)
    assert target == NOW + timedelta(minutes=5)
    assert msg == "ara"


def test_parse_tomorrow_with_time():
    target, _ = parse_reminder("yarin 09:00 -> toplanti", now=NOW)
    assert target == datetime(2026, 6, 22, 9, 0)


def test_parse_bare_time_rolls_to_tomorrow_when_past():
    target, _ = parse_reminder("08:00 -> erken", now=NOW)
    assert target == datetime(2026, 6, 22, 8, 0)


def test_parse_bare_time_today_when_future():
    target, _ = parse_reminder("18:30 -> aksam", now=NOW)
    assert target == datetime(2026, 6, 21, 18, 30)


def test_parse_default_message():
    _, msg = parse_reminder("18:30", now=NOW)
    assert msg


def test_parse_bad_format_raises():
    with pytest.raises(ValueError):
        parse_reminder("merhaba dunya", now=NOW)


def test_parse_empty_raises():
    with pytest.raises(ValueError):
        parse_reminder("   ", now=NOW)


def test_schedule_rejects_past_time_on_windows():
    if sys.platform != "win32":
        assert schedule_reminder("18:30 -> x", now=NOW)[1] == "reminder_not_windows"
        return
    ok, reason = schedule_reminder("2000-01-01 09:00 -> gecmis", now=NOW)
    assert not ok
    assert reason == "reminder_past"
