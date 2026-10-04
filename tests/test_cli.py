from mindev.cli import main


def test_cli_prints_help(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "mini-dev" in out
