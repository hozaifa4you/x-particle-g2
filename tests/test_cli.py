from typing import Any

import pytest
from typer.testing import CliRunner

import main
from src.agent import runner
from src.agent.state import TradeDecision


@pytest.fixture
def modes(monkeypatch: pytest.MonkeyPatch) -> list[bool | None]:
    seen: list[bool | None] = []

    def fake_run_once(symbols: Any = None, dry_run: bool | None = None, **_: Any) -> TradeDecision:
        seen.append(dry_run)
        return TradeDecision(dry_run=True)

    monkeypatch.setattr(runner, "run_once", fake_run_once)
    return seen


def test_once_defers_to_env_without_flag(modes: list[bool | None]) -> None:
    result = CliRunner().invoke(main.app, ["once", "--symbols", "EURUSD"])
    assert result.exit_code == 0, result.output
    assert modes == [None]


def test_dry_run_flag_forces_paper(modes: list[bool | None]) -> None:
    result = CliRunner().invoke(main.app, ["once", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert modes == [True]


def test_cli_cannot_force_live(modes: list[bool | None]) -> None:
    result = CliRunner().invoke(main.app, ["once", "--no-dry-run"])
    assert result.exit_code != 0
    assert modes == []
