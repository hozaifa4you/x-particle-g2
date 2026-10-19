from typing import Any

from pydantic import BaseModel, Field

from ..agent.state import Candidate, TradeDecision
from ..config import Settings
from ..journal.store import Journal, JournalEntry
from ..mt5_client.client import MT5Client
from ..mt5_client.enums import NAME_TO_TIMEFRAME, OrderSide, Timeframe
from ..mt5_client.errors import MT5Error
from ..mt5_client.models import Account, MarketOrderRequest, Position, Side
from ..risk.engine import GateResult, RiskEngine
from ..risk.session import day_start
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
    side: Side | None = None
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

    @property
    def settings(self) -> Settings:
        return self._settings

    def _account_gate(self) -> tuple[Account, list[Position], GateResult]:
        account = self._client.account()
        positions = self._client.positions()
        closed_today = self._client.closed_pnl_since(day_start(self._risk.utcnow()))
        return account, positions, self._risk.check_account(account, len(positions), closed_today)

    def get_account(self) -> AccountSummary:
        account, positions, gate = self._account_gate()
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
            view = analyze_symbol(self._client.candles(symbol, timeframe, 300))
            out.append(
                IndicatorView(
                    symbol=symbol, timeframe=name, trend=view.trend, rsi=view.rsi, atr=view.atr, bars=view.bars
                )
            )
        return out

    def check_conditions(self, symbol: str) -> PlanView:
        _, positions, gate = self._account_gate()
        if not gate.allowed:
            return PlanView(symbol=symbol, allowed=False, reason=gate.reason)
        now = self._risk.utcnow()
        timing = self._risk.check_timing(now, len(self._journal.today_entries(now)), self._journal.last_trade_time())
        if not timing.allowed:
            return PlanView(symbol=symbol, allowed=False, reason=timing.reason)
        if any(p.symbol == symbol for p in positions):
            return PlanView(symbol=symbol, allowed=False, reason=f"Position already open on {symbol}")
        return PlanView(symbol=symbol, allowed=True, reason="Conditions passed")

    def plan_trade(self, symbol: str, side: Side) -> Candidate:
        candidate = Candidate(symbol=symbol, side=side)
        spec = self._client.symbol(symbol)
        candles = self._client.candles(symbol, Timeframe.H1, 300)
        stops = plan_stops(
            candles, spec, side,
            atr_mult=self._settings.atr_mult, min_rr=self._settings.min_rr,
            min_sl_pips=self._settings.min_sl_pips, commission_per_lot=self._settings.commission_per_lot,
        )
        if stops is None:
            candidate.block_reason = f"Not enough H1 data for stops ({len(candles)} bars)"
            return candidate
        candidate.stops = stops
        account = self._client.account()
        sizing = self._risk.size_volume(account.equity, abs(stops.entry - stops.sl_price), spec)
        candidate.sizing_reason = sizing.reason
        if not sizing.allowed:
            candidate.block_reason = sizing.reason
            return candidate
        order_side = OrderSide.BUY if side == "BUY" else OrderSide.SELL
        required = self._client.margin_for(symbol, order_side, sizing.volume, stops.entry)
        margin = self._risk.check_margin(account, required)
        if not margin.allowed:
            candidate.block_reason = margin.reason
            return candidate
        candidate.volume = sizing.volume
        return candidate

    def validate_setup(self, candidate: Candidate) -> PlanView:
        if candidate.block_reason or candidate.stops is None:
            reason = candidate.block_reason or "No stop plan"
            return PlanView(symbol=candidate.symbol, side=candidate.side, allowed=False, reason=reason)
        spec = self._client.symbol(candidate.symbol)
        trends = {tf: "UNKNOWN" for tf in ("H1", "H4", "D1")}
        for name in self._settings.timeframe_list:
            timeframe = NAME_TO_TIMEFRAME.get(name.upper())
            if timeframe is None or name not in trends:
                continue
            trends[name] = analyze_symbol(self._client.candles(candidate.symbol, timeframe, 300)).trend
        gate = self._risk.check_setup(spec, candidate.side, candidate.stops, trends["H1"], trends["H4"], trends["D1"])
        candidate.trend_h1 = trends["H1"]
        candidate.trend_h4 = trends["H4"]
        candidate.trend_d1 = trends["D1"]
        return PlanView(
            symbol=candidate.symbol, side=candidate.side, volume=candidate.volume,
            sl_pips=candidate.stops.sl_pips, tp_pips=candidate.stops.tp_pips,
            allowed=gate.allowed, reason=gate.reason,
        )

    def place_order(self, decision: TradeDecision, dry_run: bool) -> str:
        if dry_run:
            return "paper: order not sent"
        if decision.action != "EXECUTE" or decision.side is None:
            raise ValueError(f"Refusing to send a {decision.action} decision without a side")
        spec = self._client.symbol(decision.symbol)
        order = MarketOrderRequest(
            symbol=decision.symbol, side=decision.side, volume=decision.volume,
            sl_price=decision.sl_price, tp_price=decision.tp_price,
            magic=self._settings.magic_number,
        )
        result = self._client.send_market(order, spec)
        if not result.ok:
            raise MT5Error(f"order not confirmed: {result.comment}", retcode=result.retcode)
        return f"order sent: order={result.order} deal={result.deal} price={result.price} retcode={result.retcode}"

    def log_decision(self, decision: TradeDecision) -> None:
        reason = f"{decision.reason} | {decision.outcome}" if decision.outcome else decision.reason
        self._journal.append(
            JournalEntry(
                symbol=decision.symbol, action=decision.action, side=decision.side or "",
                volume=decision.volume, reason=reason, sl_pips=decision.sl_pips,
                tp_pips=decision.tp_pips, dry_run=decision.dry_run,
            )
        )


def langchain_tools(toolkit: Toolkit) -> list[Any]:
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel

    class SymbolIn(BaseModel):
        symbol: str = Field(min_length=1)

    class PlanIn(BaseModel):
        symbol: str = Field(min_length=1)
        side: Side = "BUY"

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
            func=lambda: f"{toolkit.settings.symbol_list}",
            name="list_symbols", description="Configured trading universe.",
        ),
    ]
