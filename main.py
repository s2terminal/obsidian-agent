import sys
from pathlib import Path
from typing import Annotated

import typer

# scripts/ を import ルートに加え、reader / common / research を
# トップレベルパッケージとして絶対 import できるようにする（pytest の pythonpath と一致）
sys.path.insert(0, str(Path(__file__).parent / "scripts"))

app = typer.Typer(no_args_is_help=True)
reader_app = typer.Typer()
research_app = typer.Typer()


@app.callback()
def cli() -> None:
    """Obsidian Agent CLI。"""


@reader_app.callback(invoke_without_command=True)
def reader(
    ctx: typer.Context,
    summarize_only: Annotated[
        bool,
        typer.Option(
            "--summarize-only",
            help="要約を生成して標準出力に流します。last_fetched と要約ファイルは更新しません",
        ),
    ] = False,
):
    """RSS reader を実行します。"""
    if ctx.invoked_subcommand is not None:
        return
    from reader.main import run as run_reader_main
    run_reader_main(summarize_only=summarize_only)


@reader_app.command("check")
def reader_check() -> None:
    """フィード設定を読み込んで内容を表示します。"""
    from reader.checker import check
    check()


@research_app.callback(invoke_without_command=True)
def research(
    query: Annotated[list[str], typer.Argument(help="リサーチ内容")],
) -> None:
    """Deep Research を実行します。"""
    from research.main import run as run_research
    run_research(" ".join(query))


app.add_typer(reader_app, name="reader")
app.add_typer(research_app, name="research")

if __name__ == "__main__":
    app()
