from typing import Annotated

import typer

from scripts.reader.main import run as run_reader_main

app = typer.Typer(no_args_is_help=True)
reader_app = typer.Typer()


@app.callback()
def cli() -> None:
    """Obsidian Agent CLI。"""


@reader_app.callback(invoke_without_command=True)
def reader(
    summarize_only: Annotated[
        bool,
        typer.Option(
            "--summarize-only",
            help="要約を生成して標準出力に流します。last_fetched と要約ファイルは更新しません",
        ),
    ] = False,
):
    """RSS reader を実行します。"""
    run_reader_main(summarize_only=summarize_only)


app.add_typer(reader_app, name="reader")

if __name__ == "__main__":
    app()
