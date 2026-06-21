from ui_terminal import print_option


def test_print_option_includes_description(capsys):
    print_option("1", "Test", "Short description.")
    out = capsys.readouterr().out
    assert "1) Test" in out
    assert "Short description." in out
