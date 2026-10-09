from __future__ import annotations

import typer

app = typer.Typer(no_args_is_help=True, help="X-Particle G2 conservative forex trader.")


@app.command()
def once(
    symbols: str = typer.Option("", help="Comma separated symbols, overrides SYMBOLS"),
    dry_run: bool = typer.Option(True, help="Plan and validate without sending orders"),
) -> None:
    from src.agent.runner import run_once

    decision = run_once(symbols=symbols or None, dry_run=dry_run)
    typer.echo(decision.describe())


@app.command()
def loop(
    interval_min: int = typer.Option(30, min=5, max=240),
    symbols: str = typer.Option("", help="Comma separated symbols, overrides SYMBOLS"),
    dry_run: bool = typer.Option(True),
) -> None:
    import time

    from src.agent.runner import run_once

    while True:
        decision = run_once(symbols=symbols or None, dry_run=dry_run)
        typer.echo(decision.describe())
        time.sleep(interval_min * 60)


@app.command()
def backtest(
    symbol: str = typer.Option("EURUSDm"),
    timeframe: str = typer.Option("H1"),
    count: int = typer.Option(500, min=100, max=5000),
) -> None:
    from src.backtest.engine import summarize

    typer.echo(summarize(symbol=symbol, timeframe=timeframe, count=count))


if __name__ == "__main__":
    app()
