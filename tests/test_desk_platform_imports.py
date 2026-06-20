def test_close_process_has_ensure_windows():
    from desk_platform import automation

    assert callable(getattr(automation, "_ensure_windows", None))


def test_platform_actions_close_import():
    from platform_actions import close_process

    assert callable(close_process)
