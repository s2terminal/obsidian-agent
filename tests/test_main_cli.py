from typer.testing import CliRunner

import main as cli_main


runner = CliRunner()


def test_reader_command_calls_reader_main(monkeypatch):
    called: dict[str, bool] = {}

    def fake_reader_main(*, summarize_only: bool = False):
        called["summarize_only"] = summarize_only

    monkeypatch.setattr(cli_main, "run_reader_main", fake_reader_main)

    result = runner.invoke(cli_main.app, ["reader", "--summarize-only"])

    assert result.exit_code == 0
    assert called == {"summarize_only": True}


def test_reader_command_defaults_to_full_run(monkeypatch):
    called: dict[str, bool] = {}

    def fake_reader_main(*, summarize_only: bool = False):
        called["summarize_only"] = summarize_only

    monkeypatch.setattr(cli_main, "run_reader_main", fake_reader_main)

    result = runner.invoke(cli_main.app, ["reader"])

    assert result.exit_code == 0
    assert called == {"summarize_only": False}
