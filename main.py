import typer

app = typer.Typer()

@app.command()
def reader(summarizeOnly: bool = False):
    # 処理...
    pass

if __name__ == "__main__":
    app()
