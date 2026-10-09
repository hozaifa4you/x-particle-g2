from typing import Any

from pydantic import BaseModel, Field

from ..agent.state import Candidate
from ..config import Settings
from ..journal.store import Journal
from ..mt5_client.client import MT5Client
from ..mt5_client.enums import NAME_TO_TIMEFRAME
from ..mt5_client.models import MarketOrderRequest
from ..risk.engine import RiskEngine
from ..strategy.stops import analyze_symbol, plan_stops


class AccountSummary(BaseModel):
    balance: float = 0.0
    equity: float = 0.0
    margin_level: float = 0.0
    open_positions: int = 0
    can_trade: bool = False
    reason: str = ""


class SymbolState(BaseModel):
    symbol: str = ""
    bid: float = 0.0
    ask: float = 0.0
    spread_pips: float = 0.0
    digits: int = 5


class IndicatorView(BaseModel):
    symbol: str = ""
    timeframe: str = ""
    trend: str = "UNKNOWN"
    rsi: float | None = None
    atr: float | None = None
    bars: int = 0


class PlanView(BaseModel):
    symbol: str = ""
    side: str = ""
    volume: float = 0.0
    sl_pips: float = 0.0
    tp_pips: float = 0.0
    allowed: bool = False
    reason: str = ""


class Toolkit:
    def __init__(self, client: MT5Client, settings: Settings, risk: RiskEngine, journal: Journal) -> None:
        self._client = client
        self._settings = settings
        self._risk = risk
        self._journal = journal

    def get_account(self) -> AccountSummary:
        account = self._client.account()
        positions = self._client.positions()
        gate = self._risk.check_account(account, len(positions))
        return AccountSummary(
            balance=account.balance,
            equity=account.equity,
            margin_level=account.margin_level,
            open_positions=len(positions),
            can_trade=gate.allowed,
            reason=gate.reason,
        )

    def get_symbol_state(self, symbol: str) -> SymbolState:
        spec = self._client.symbol(symbol)
        return SymbolState(
            symbol=symbol, bid=spec.bid, ask=spec.ask, spread_pips=spec.spread_pips(), digits=spec.digits
        )

    def get_indicators_mtf(self, symbol: str) -> list[IndicatorView]:
        out: list[IndicatorView] = []
        for name in self._settings.timeframe_list:
            timeframe = NAME_TO_TIMEFRAME.get(name.upper())
            if timeframe is None:
                continue
            candles = self._client.candles(symbol, timeframe, 300)
            view = analyze_symbol(candles)
            out.append(
                IndicatorView(
                    symbol=symbol, timeframe=name, trend=str(view["trend"]), rsi=view["rsi"],
                    atr=view["atr"], bars=int(view["bars"]),
                )
            )
        return out

    def check_conditions(self, symbol: str) -> PlanView:
        account = self._client.account()
        positions = self._client.positions()
        gate = self._risk.check_account(account, len(positions))
        if not gate.allowed:
            return PlanView(symbol=symbol, allowed=False, reason=gate.reason)
        timing = self._risk.check_timing(
            self._risk.utcnow(),
            len(self._journal.today_entries(self._risk.utcnow())),
            self._journal.last_trade_time(),
        )
        if not timing.allowed:
            return PlanView(symbol=symbol, allowed=False, reason=timing.reason)
        if any(p.symbol == symbol for p in positions):
            return PlanView(symbol=symbol, allowed=False, reason=f"Position already open on {symbol}")
        return PlanView(symbol=symbol, allowed=True, reason="Conditions passed")

    def plan_trade(self, symbol: str, side: str) -> Candidate:
        candidate = Candidate(symbol=symbol, side=side)
        spec = self._client.symbol(symbol)
        timeframe = NAME_TO_TIMEFRAME.get("H1")
        if timeframe is None:
            candidate.block_reason = "H1 timeframe missing"
            return candidate
        candles = self._client.candles(symbol, timeframe, 300)
        stops = plan_stops(
            candles, spec, side,
            atr_mult=self._settings.atr_mult, min_rr=self._settings.min_rr,
            min_sl_pips=self._settings.min_sl_pips,
        )
        if stops is None:
            candidate.block_reason = "Not enough data for stops"
            return candidate
        account = self._client.account()
        sl_dist = abs(
            (spec.ask if side == "BUY" else spec.bid) - stops.sl_price
        )
        volume = self._risk.size_volume(account.equity, sl_dist, spec)
        volume = self._client.normalize_volume(spec, volume)
        candidate.sl_pips = stops.sl_pips
        candidate.tp_pips = stops.tp_pips
        candidate.sl_price = stops.sl_price
        candidate.tp_price = stops.tp_price
        candidate.volume = volume
        return candidate

    def validate_setup(self, candidate: Candidate) -> PlanView:
        spec = self._client.symbol(candidate.symbol)
        trends = {tf: "UNKNOWN" for tf in ("H1", "H4", "D1")}
        for name in self._settings.timeframe_list:
            timeframe = NAME_TO_TIMEFRAME.get(name.upper())
            if timeframe is None or name not in trends:
                continue
            candles = self._client.candles(candidate.symbol, timeframe, 300)
            trends[name] = str(analyze_symbol(candles)["trend"])
        gate = self._risk.check_setup(
            spec, candidate.side, candidate.sl_pips, candidate.tp_pips,
            trends.get("H1", "UNKNOWN"), trends.get("H4", "UNKNOWN"), trends.get("D1", "UNKNOWN"),
        )
        candidate.trend_h1 = trends.get("H1", "UNKNOWN")
        candidate.trend_h4 = trends.get("H4", "UNKNOWN")
        candidate.trend_d1 = trends.get("D1", "UNKNOWN")
        return PlanView(
            symbol=candidate.symbol, side=candidate.side, volume=candidate.volume,
            sl_pips=candidate.sl_pips, tp_pips=candidate.tp_pips,
            allowed=gate.allowed, reason=gate.reason,
        )

    def place_order(self, candidate: Candidate, dry_run: bool) -> str:
        if dry_run:
            return "paper: order not sent"
        spec = self._client.symbol(candidate.symbol)
        order = MarketOrderRequest(
            symbol=candidate.symbol, side=candidate.side, volume=candidate.volume,
            sl_price=candidate.sl_price, tp_price=candidate.tp_price,
            magic=self._settings.magic_number,
        )
        result = self._client.send_market(order, spec)
        return f"order={result.order} deal={result.deal} price={result.price}"

    def log_decision(self, symbol: str, action: str, reason: str, dry_run: bool) -> None:
        from ..journal.store import JournalEntry

        self._journal.append(
            JournalEntry(symbol=symbol, action=action, reason=reason, dry_run=dry_run)
        )


def langchain_tools(toolkit: Toolkit) -> list[Any]:
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel

    class SymbolIn(BaseModel):
        symbol: str = Field(min_length=1)

    class PlanIn(BaseModel):
        symbol: str = Field(min_length=1)
        side: str = "BUY"

    return [
        StructuredTool.from_function(
            func=lambda: toolkit.get_account().model_dump_json(),
            name="get_account", description="Account balance, margin, and trading permission.",
        ),
        StructuredTool.from_function(
            func=lambda symbol: toolkit.get_symbol_state(symbol).model_dump_json(),
            name="get_symbol_state", description="Live quote and spread for a symbol.",
            args_schema=SymbolIn,
        ),
        StructuredTool.from_function(
            func=lambda symbol: f"{[v.model_dump() for v in toolkit.get_indicators_mtf(symbol)]}",
            name="get_indicators_mtf", description="H1/H4/D1 trend, RSI, ATR per symbol.",
            args_schema=SymbolIn,
        ),
        StructuredTool.from_function(
            func=lambda symbol: toolkit.check_conditions(symbol).model_dump_json(),
            name="check_conditions", description="Account, timing, and exposure gates.",
            args_schema=SymbolIn,
        ),
        StructuredTool.from_function(
            func=lambda symbol, side: toolkit.plan_trade(symbol, side).model_dump_json(),
            name="plan_trade", description="ATR stops plus risk-sized volume.",
            args_schema=PlanIn,
        ),
        StructuredTool.from_function(
            func=lambda symbol, side: toolkit.validate_setup(
                toolkit.plan_trade(symbol, side)
            ).model_dump_json(),
            name="validate_setup", description="Validate spread, stops, reward, alignment.",
            args_schema=PlanIn,
        ),
        StructuredTool.from_function(
            func=lambda: "decisions are written to the journal",
            name="log_decision", description="Record the final decision.",
        ),
        StructuredTool.from_function(
            func=lambda: f"{toolkit._settings.symbol_list}",
            name="list_symbols", description="Configured trading universe.",
        ),
    ]
