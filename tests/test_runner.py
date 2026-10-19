import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from src.agent.graph import build_graph
from src.agent.runner import run_once
from src.journal.store import Journal, JournalEntry
from src.mt5_client.client import MT5Client
from src.risk.engine import RiskEngine
from src.tools.trading_tools import Toolkit
from tests.helpers import FakeBackend, as_rows, make_settings, trend_candles

WEDNESDAY = datetime(2026, 1, 7, 10, 0, tzinfo=UTC)


@pytest.mark.parametrize("module", ["src.tools", "src.agent", "src.risk"])
def test_packages_import_on_their_own(module: str) -> None:
    done = subprocess.run([sys.executable, "-c", f"import {module}"], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def test_offline_run_writes_no_trade(tmp_path: Path) -> None:
    backend = FakeBackend()
    backend.connect_ok = False
    active = make_settings(journal_path=str(tmp_path / "history.jsonl"), openrouter_api_key="")
    decision = run_once(symbols="EURUSD", dry_run=True, active=active, backend=backend)  # type: ignore[arg-type]
    assert decision.action == "NO_TRADE"
    assert "MT5 unavailable" in decision.reason
    assert (tmp_path / "history.jsonl").exists()


def test_journal_filters_today(tmp_path: Path) -> None:
    journal = Journal(str(tmp_path / "j.jsonl"))
    journal.append(JournalEntry(symbol="EURUSD", action="EXECUTE", reason="t", dry_run=True))
    assert len(journal.today_entries(datetime.now(UTC))) == 1
    assert journal.last_trade_time() is not None


def test_journal_stamps_each_entry_when_created() -> None:
    # A class-level default froze every entry at import time, breaking cooldowns in `loop`.
    before = datetime.now(UTC)
    assert JournalEntry().time >= before


def run_graph(tmp_path: Path, dry_run: bool) -> tuple[dict[str, Any], FakeBackend, list[dict[str, Any]]]:
    backend = FakeBackend()
    backend.rates = as_rows(trend_candles(250))
    active = make_settings(journal_path=str(tmp_path / "j.jsonl"), openrouter_api_key="", dry_run=dry_run)
    client = MT5Client(active, backend=backend)  # type: ignore[arg-type]
    client.connect()
    toolkit = Toolkit(client, active, RiskEngine(active, clock=lambda: WEDNESDAY), Journal(active.journal_path))
    result = build_graph(toolkit, ["EURUSD"], dry_run).invoke({"symbols": ["EURUSD"], "dry_run": dry_run})
    lines = (tmp_path / "j.jsonl").read_text(encoding="utf-8").splitlines()
    return result["decision"], backend, [json.loads(line) for line in lines]


def test_paper_run_executes_without_sending(tmp_path: Path) -> None:
    decision, backend, journal = run_graph(tmp_path, dry_run=True)
    assert decision["action"] == "EXECUTE", decision["reason"]
    assert decision["outcome"] == "paper: order not sent"
    assert backend.sent == []
    assert journal[-1]["side"] == "BUY" and journal[-1]["volume"] == decision["volume"] > 0
    assert "paper: order not sent" in journal[-1]["reason"]


def test_live_run_sends_the_validated_prices(tmp_path: Path) -> None:
    decision, backend, _ = run_graph(tmp_path, dry_run=False)
    assert decision["action"] == "EXECUTE", decision["reason"]
    assert len(backend.sent) == 1
    order = backend.sent[0]
    sent = (order["volume"], order["sl"], order["tp"])
    assert sent == (decision["volume"], decision["sl_price"], decision["tp_price"])
    assert decision["outcome"].startswith("order sent")
