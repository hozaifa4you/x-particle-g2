from typing import Any, Literal

from pydantic import BaseModel
from typing_extensions import TypedDict

from ..mt5_client.models import Side
from ..strategy.stops import StopPlan


class TradeDecision(BaseModel):
    action: Literal["EXECUTE", "NO_TRADE"] = "NO_TRADE"
    symbol: str = ""
    side: Side | None = None
    volume: float = 0.0
    sl_pips: float = 0.0
    tp_pips: float = 0.0
    sl_price: float = 0.0
    tp_price: float = 0.0
    reason: str = "No setup evaluated"
    outcome: str = ""
    dry_run: bool = True

    def describe(self) -> str:
        mode = "PAPER" if self.dry_run else "LIVE"
        if self.action == "EXECUTE":
            return (
                f"TRADE DECISION: EXECUTE [{mode}]\nSymbol: {self.symbol}\nDirection: {self.side}\n"
                f"Volume: {self.volume} lots\nStop: {self.sl_pips:.1f} pips @ {self.sl_price}\n"
                f"Take: {self.tp_pips:.1f} pips @ {self.tp_price}\nReason: {self.reason}\n"
                f"Outcome: {self.outcome or 'not executed'}"
            )
        return f"TRADE DECISION: NO TRADE [{mode}]\nReason: {self.reason}"


class Candidate(BaseModel):
    symbol: str = ""
    side: Side = "BUY"
    trend_h1: str = "UNKNOWN"
    trend_h4: str = "UNKNOWN"
    trend_d1: str = "UNKNOWN"
    stops: StopPlan | None = None
    volume: float = 0.0
    sizing_reason: str = ""
    block_reason: str = ""


class AgentState(TypedDict, total=False):
    symbols: list[str]
    candidates: list[dict[str, Any]]
    decision: dict[str, Any]
    dry_run: bool
    notes: list[str]
    extra: dict[str, object]
