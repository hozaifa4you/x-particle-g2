from typing import Any

from pydantic import BaseModel

from ..mt5_client.models import Candle, SymbolSpec
from . import indicators as ind


class StopPlan(BaseModel):
    sl_pips: float = 0.0
    tp_pips: float = 0.0
    sl_price: float = 0.0
    tp_price: float = 0.0
    atr_price: float = 0.0


def plan_stops(
    candles: list[Candle],
    spec: SymbolSpec,
    side: str,
    atr_mult: float = 2.0,
    min_rr: float = 2.0,
    min_sl_pips: float = 10.0,
) -> StopPlan | None:
    value = ind.atr(candles)
    if value is None or value <= 0:
        return None
    pip = spec.pips_per_price()
    spread = spec.spread_pips()
    raw_sl = max(value * atr_mult / pip, min_sl_pips, spread * 3)
    raw_tp = raw_sl * min_rr
    entry = spec.ask if side == "BUY" else spec.bid
    if side == "BUY":
        sl_price = entry - raw_sl * pip
        tp_price = entry + raw_tp * pip
    else:
        sl_price = entry + raw_sl * pip
        tp_price = entry - raw_tp * pip
    return StopPlan(
        sl_pips=round(raw_sl, 1),
        tp_pips=round(raw_tp, 1),
        sl_price=round(sl_price, spec.digits),
        tp_price=round(tp_price, spec.digits),
        atr_price=value,
    )


def analyze_symbol(candles: list[Candle]) -> dict[str, Any]:
    values = ind.closes(candles)
    return {
        "ema50": ind.ema(values, 50),
        "ema200": ind.ema(values, 200),
        "rsi": ind.rsi(values),
        "macd": ind.macd(values),
        "atr": ind.atr(candles),
        "bollinger": ind.bollinger(values),
        "trend": ind.trend_of(values),
        "levels": ind.support_resistance(candles),
        "bars": len(candles),
    }
