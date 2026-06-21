from shell_guard import blocked_shell_reason


def test_blocks_format_drive():
    assert blocked_shell_reason("format C: /y") == "format_drive"


def test_blocks_powershell_recurse_delete():
    assert blocked_shell_reason("Remove-Item C:\\ -Recurse -Force") == "mass_delete_ps"


def test_allows_safe_commands():
    assert blocked_shell_reason("dir") is None
    assert blocked_shell_reason("echo hello") is None
