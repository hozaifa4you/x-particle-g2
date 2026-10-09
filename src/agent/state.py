from typing import Any, Literal

from pydantic import BaseModel
from typing_extensions import TypedDict


class TradeDecision(BaseModel):
    action: Literal["EXECUTE", "NO_TRADE"] = "NO_TRADE"
    symbol: str = ""
    side: str = ""
    volume: float = 0.0
    sl_pips: float = 0.0
    tp_pips: float = 0.0
    reason: str = "No setup evaluated"
    dry_run: bool = True

    def describe(self) -> str:
        if self.action == "EXECUTE":
            return (
                f"TRADE DECISION: EXECUTE\nSymbol: {self.symbol}\nDirection: {self.side}\n"
                f"Volume: {self.volume} lots\nStop: {self.sl_pips} pips\nTake: {self.tp_pips} pips\n"
                f"Reason: {self.reason}"
            )
        return f"TRADE DECISION: NO TRADE\nReason: {self.reason}"


class Candidate(BaseModel):
    symbol: str = ""
    side: str = ""
    trend_h1: str = "UNKNOWN"
    trend_h4: str = "UNKNOWN"
    trend_d1: str = "UNKNOWN"
    sl_pips: float = 0.0
    tp_pips: float = 0.0
    sl_price: float = 0.0
    tp_price: float = 0.0
    volume: float = 0.0
    block_reason: str = ""


class AgentState(TypedDict, total=False):
    symbols: list[str]
    candidates: list[dict[str, Any]]
    decision: dict[str, Any]
    dry_run: bool
    notes: list[str]
    extra: dict[str, object]
