import math
from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import BaseModel

from ..config import Settings
from ..mt5_client.models import Account, Side, SymbolSpec
from ..strategy.stops import StopPlan
from .session import cooldown_remaining, is_friday_lockout, is_off_day

# Tolerance for float noise when comparing exact integer-point ratios against limits.
RATIO_EPSILON = 1e-9


class GateResult(BaseModel):
    allowed: bool = False
    reason: str = ""
    volume: float = 0.0


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RiskEngine:
    def __init__(self, settings: Settings, clock: Callable[[], datetime] = _utcnow) -> None:
        self._settings = settings
        self._clock = clock

    def size_volume(self, equity: float, sl_price_dist: float, spec: SymbolSpec) -> GateResult:
        if equity <= 0:
            return GateResult(allowed=False, reason="Equity unavailable for sizing")
        if sl_price_dist <= 0:
            return GateResult(allowed=False, reason="Stop distance is zero")
        if spec.tick_size <= 0 or spec.tick_value <= 0 or spec.volume_step <= 0:
            return GateResult(allowed=False, reason=f"{spec.name} contract data missing for sizing")
        risk_pct = self._settings.risk_pct
        loss_per_lot = sl_price_dist / spec.tick_size * spec.tick_value + self._settings.commission_per_lot
        raw = equity * risk_pct / 100 / loss_per_lot
        # Floor to the broker step: rounding up would breach the risk limit.
        steps = math.floor(min(raw, spec.volume_max) / spec.volume_step + RATIO_EPSILON)
        volume = round(steps * spec.volume_step, 8)
        if volume < spec.volume_min:
            min_risk = spec.volume_min * loss_per_lot / equity * 100
            return GateResult(
                allowed=False,
                reason=f"Min lot {spec.volume_min} risks {min_risk:.2f}%, above the {risk_pct}% limit",
            )
        actual = volume * loss_per_lot / equity * 100
        return GateResult(allowed=True, reason=f"Risk {actual:.2f}% at {volume} lots", volume=volume)

    def check_account(self, account: Account, open_count: int, closed_pnl_today: float) -> GateResult:
        if not account.trade_allowed:
            return GateResult(allowed=False, reason="Broker has disabled algo trading")
        if account.margin_level and account.margin_level < self._settings.min_margin_level:
            return GateResult(allowed=False, reason=f"Margin level {account.margin_level:.0f}% below minimum")
        if open_count >= self._settings.max_concurrent_positions:
            return GateResult(allowed=False, reason="Max concurrent positions reached")
        # Balance already includes today's closed result, so removing it recovers the day-start basis.
        day_start = account.balance - closed_pnl_today
        if day_start <= 0:
            return GateResult(allowed=False, reason="Day-start balance unavailable")
        day_pnl = closed_pnl_today + account.profit
        limit_pct = self._settings.max_daily_loss_pct
        if day_pnl <= -(day_start * limit_pct / 100):
            lost_pct = -day_pnl / day_start * 100
            return GateResult(
                allowed=False,
                reason=f"Daily loss limit hit: {day_pnl:.2f} {account.currency} ({lost_pct:.2f}% >= {limit_pct}%)",
            )
        return GateResult(allowed=True, reason="Account gates passed")

    def check_margin(self, account: Account, required_margin: float) -> GateResult:
        used = account.margin + required_margin
        if used <= 0:
            return GateResult(allowed=True, reason="No margin required")
        projected = account.equity / used * 100
        if projected < self._settings.min_margin_level:
            return GateResult(
                allowed=False, reason=f"Margin level after entry {projected:.0f}% below minimum"
            )
        return GateResult(allowed=True, reason=f"Margin level after entry {projected:.0f}%")

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
        side: Side,
        plan: StopPlan,
        trend_h1: str,
        trend_h4: str,
        trend_d1: str,
    ) -> GateResult:
        spread = spec.spread_pips()
        if spread > self._settings.max_spread_pips:
            return GateResult(allowed=False, reason=f"Spread {spread:.1f} pips too wide")
        if plan.sl_pips < self._settings.min_sl_pips:
            return GateResult(allowed=False, reason="Stop too tight for noise")
        if plan.sl_pips < spread * 3:
            return GateResult(allowed=False, reason="Stop too close to spread cost")
        point_value = spec.point_value()
        if point_value <= 0 or plan.sl_points <= 0:
            return GateResult(allowed=False, reason=f"{spec.name} contract data missing for reward check")
        cost = self._settings.commission_per_lot / point_value
        rr = (plan.tp_points - cost) / (plan.sl_points + cost)
        if rr + RATIO_EPSILON < self._settings.min_rr:
            return GateResult(allowed=False, reason=f"Net reward {rr:.3f}R below minimum")
        trends = {trend_h1, trend_h4, trend_d1}
        want = "BULLISH" if side == "BUY" else "BEARISH"
        if trends != {want}:
            return GateResult(allowed=False, reason="Timeframes do not align")
        return GateResult(allowed=True, reason="Setup gates passed")

    def utcnow(self) -> datetime:
        return self._clock()
