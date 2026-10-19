import math

from pydantic import BaseModel

from ..mt5_client.models import Candle, Side, SymbolSpec
from . import indicators as ind


class StopPlan(BaseModel):
    entry: float = 0.0
    sl_points: int = 0
    tp_points: int = 0
    sl_pips: float = 0.0
    tp_pips: float = 0.0
    sl_price: float = 0.0
    tp_price: float = 0.0
    atr_price: float = 0.0


class IndicatorSnapshot(BaseModel):
    model_config = {"frozen": True}

    ema50: float | None = None
    ema200: float | None = None
    rsi: float | None = None
    macd: dict[str, float] | None = None
    atr: float | None = None
    bollinger: dict[str, float] | None = None
    trend: str = "UNKNOWN"
    levels: dict[str, list[float]] = {}
    bars: int = 0


def plan_stops(
    candles: list[Candle],
    spec: SymbolSpec,
    side: Side,
    atr_mult: float = 2.0,
    min_rr: float = 2.0,
    min_sl_pips: float = 10.0,
    commission_per_lot: float = 0.0,
) -> StopPlan | None:
    value = ind.atr(candles)
    point_value = spec.point_value()
    if value is None or value <= 0 or spec.point <= 0 or point_value <= 0:
        return None
    pip_points = spec.pip() / spec.point
    spread_points = (spec.ask - spec.bid) / spec.point
    # Whole points keep the ratio exact after prices snap to the broker grid; the epsilon absorbs float noise.
    sl_points = math.ceil(max(value * atr_mult / spec.point, min_sl_pips * pip_points, spread_points * 3) - 1e-6)
    cost_points = commission_per_lot / point_value
    tp_points = math.ceil(min_rr * (sl_points + cost_points) + cost_points)
    entry = spec.ask if side == "BUY" else spec.bid
    direction = 1 if side == "BUY" else -1
    return StopPlan(
        entry=entry,
        sl_points=sl_points,
        tp_points=tp_points,
        sl_pips=sl_points / pip_points,
        tp_pips=tp_points / pip_points,
        sl_price=round(entry - direction * sl_points * spec.point, spec.digits),
        tp_price=round(entry + direction * tp_points * spec.point, spec.digits),
        atr_price=value,
    )


def analyze_symbol(candles: list[Candle]) -> IndicatorSnapshot:
    values = ind.closes(candles)
    return IndicatorSnapshot(
        ema50=ind.ema(values, 50),
        ema200=ind.ema(values, 200),
        rsi=ind.rsi(values),
        macd=ind.macd(values),
        atr=ind.atr(candles),
        bollinger=ind.bollinger(values),
        trend=ind.trend_of(values),
        levels=ind.support_resistance(candles),
        bars=len(candles),
    )
