from datetime import UTC, datetime

from src.agent.runner import run_once
from src.config import Settings
from src.journal.store import Journal, JournalEntry


def test_offline_run_writes_no_trade(tmp_path) -> None:
    journal_path = str(tmp_path / "history.jsonl")
    active = Settings(
        mt5_login="1", mt5_password="x", mt5_server="bad",
        journal_path=journal_path, openrouter_api_key="",
    )
    decision = run_once(symbols="EURUSDm", dry_run=True, active=active)
    assert decision.action == "NO_TRADE"
    assert "MT5" in decision.reason or "Backend" in decision.reason or "failed" in decision.reason.lower()
    assert (tmp_path / "history.jsonl").exists()


def test_journal_filters_today(tmp_path) -> None:
    journal = Journal(str(tmp_path / "j.jsonl"))
    journal.append(JournalEntry(symbol="EURUSDm", action="EXECUTE", reason="t", dry_run=True))
    now = datetime.now(UTC)
    assert len(journal.today_entries(now)) == 1
    assert journal.last_trade_time() is not None
