from datetime import UTC, datetime

from pydantic import BaseModel

from ..config import Settings
from ..mt5_client.models import Account, SymbolSpec
from .session import cooldown_remaining, is_friday_lockout, is_off_day


class GateResult(BaseModel):
    allowed: bool = False
    reason: str = ""
    volume: float = 0.0


class RiskEngine:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def size_volume(self, equity: float, sl_price_dist: float, spec: SymbolSpec) -> float:
        if sl_price_dist <= 0 or spec.tick_size <= 0 or spec.tick_value <= 0:
            return spec.volume_min
        risk_money = equity * (self._settings.risk_pct / 100)
        ticks_at_risk = sl_price_dist / spec.tick_size
        raw = risk_money / (ticks_at_risk * spec.tick_value)
        step = spec.volume_step if spec.volume_step > 0 else 0.01
        clamped = min(max(raw, spec.volume_min), spec.volume_max)
        return round(round(clamped / step) * step, 8)

    def check_account(self, account: Account, open_count: int) -> GateResult:
        if not account.trade_allowed:
            return GateResult(allowed=False, reason="Broker has disabled algo trading")
        if account.margin_level and account.margin_level < self._settings.min_margin_level:
            return GateResult(allowed=False, reason=f"Margin level {account.margin_level:.0f}% below minimum")
        if open_count >= self._settings.max_concurrent_positions:
            return GateResult(allowed=False, reason="Max concurrent positions reached")
        day_loss = account.profit
        limit = account.balance * (self._settings.max_daily_loss_pct / 100)
        if day_loss < 0 and abs(day_loss) >= limit:
            return GateResult(allowed=False, reason="Daily loss limit hit")
        return GateResult(allowed=True, reason="Account gates passed")

    def check_timing(
        self,
        now: datetime,
        trades_today: int,
        last_trade: datetime | None,
    ) -> GateResult:
        if is_off_day(now, self._settings.off_day_list):
            return GateResult(allowed=False, reason="Market closed for off day")
        if is_friday_lockout(now, self._settings.friday_cutoff_hour):
            return GateResult(allowed=False, reason="Friday cutoff passed")
        if trades_today >= self._settings.max_trades_per_day:
            return GateResult(allowed=False, reason="Daily trade limit reached")
        wait = cooldown_remaining(last_trade, now, self._settings.cooldown_min)
        if wait > 0:
            return GateResult(allowed=False, reason=f"Cooldown active, {wait} min left")
        return GateResult(allowed=True, reason="Timing gates passed")

    def check_setup(
        self,
        spec: SymbolSpec,
        side: str,
        sl_pips: float,
        tp_pips: float,
        trend_h1: str,
        trend_h4: str,
        trend_d1: str,
    ) -> GateResult:
        if spec.spread_pips() > self._settings.max_spread_pips:
            return GateResult(allowed=False, reason="Spread too wide")
        if sl_pips < self._settings.min_sl_pips:
            return GateResult(allowed=False, reason="Stop too tight for noise")
        if sl_pips < spec.spread_pips() * 3:
            return GateResult(allowed=False, reason="Stop too close to spread cost")
        rr = (tp_pips / sl_pips) if sl_pips else 0
        if rr < self._settings.min_rr:
            return GateResult(allowed=False, reason=f"Reward {rr:.2f}R below minimum")
        trends = {trend_h1, trend_h4, trend_d1}
        want = "BULLISH" if side == "BUY" else "BEARISH"
        if trends != {want}:
            return GateResult(allowed=False, reason="Timeframes do not align")
        return GateResult(allowed=True, reason="Setup gates passed")

    def utcnow(self) -> datetime:
        return datetime.now(UTC)
