import structlog

from ..config import Settings, settings
from ..journal.store import Journal, JournalEntry
from ..mt5_client.client import mt5_session
from ..mt5_client.errors import MT5Error
from ..risk.engine import RiskEngine
from ..tools.trading_tools import Toolkit
from .graph import build_graph
from .state import TradeDecision

log = structlog.get_logger("x-particle")


def run_once(
    symbols: list[str] | str | None = None,
    dry_run: bool | None = None,
    active: Settings | None = None,
) -> TradeDecision:
    active = active or settings
    names = _symbol_list(symbols, active)
    dry = active.dry_run if dry_run is None else dry_run
    journal = Journal(active.journal_path)
    try:
        with mt5_session(active) as client:
            toolkit = Toolkit(client, active, RiskEngine(active), journal)
            graph = build_graph(toolkit, names, dry)
            result = graph.invoke({"symbols": names, "dry_run": dry}, {"recursion_limit": 25})
            return _first_decision(result, names, dry, journal, "Graph run finished")
    except MT5Error as exc:
        reason = f"MT5 unavailable: {exc}"
    except ImportError as exc:
        reason = f"Backend missing: {exc}"
    except Exception as exc:
        reason = f"Run failed safely: {exc}"
    log.info("no_trade", reason=reason)
    journal.append(JournalEntry(symbol=",".join(names), action="NO_TRADE", reason=reason, dry_run=True))
    return TradeDecision(action="NO_TRADE", reason=reason, dry_run=True)


def _symbol_list(symbols: list[str] | str | None, active: Settings) -> list[str]:
    if isinstance(symbols, str):
        return [s.strip() for s in symbols.split(",") if s.strip()]
    return symbols or active.symbol_list


def _first_decision(result: object, names: list[str], dry: bool, journal: Journal, fallback: str) -> TradeDecision:
    if isinstance(result, dict):
        raw = result.get("decision", {})
        if isinstance(raw, dict) and raw.get("action") in ("EXECUTE", "NO_TRADE"):
            return TradeDecision.model_validate({**raw, "dry_run": dry})
    journal.append(JournalEntry(symbol=",".join(names), action="NO_TRADE", reason=fallback, dry_run=True))
    return TradeDecision(action="NO_TRADE", reason=fallback, dry_run=True)
