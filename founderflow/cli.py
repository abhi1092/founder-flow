import typer

app = typer.Typer(name="founderflow", help="Multi-agent startup idea validation")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        typer.echo("FounderFlow v0.1.0 — run 'founderflow --help' for usage")
