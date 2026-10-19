import math

import pytest

from src.mt5_client.models import SymbolSpec
from src.risk.engine import RiskEngine
from src.strategy.stops import plan_stops
from tests.helpers import flat_candles, make_settings


def eurusd() -> SymbolSpec:
    return SymbolSpec(
        name="EURUSD", digits=5, point=0.00001, bid=1.12062, ask=1.12063,
        volume_min=0.01, volume_max=5.0, volume_step=0.01, tick_value=1.0, tick_size=0.00001,
    )


def test_reward_never_rounds_below_minimum() -> None:
    # Before the fix, rounding pips separately rejected about a quarter of valid ATR stops as 1.99R.
    engine = RiskEngine(make_settings())
    for step in range(500, 2500, 7):
        candles = flat_candles(60, price=1.12, half_range=step / 2 * 1e-6)
        stops = plan_stops(candles, eurusd(), "BUY")
        assert stops is not None
        verdict = engine.check_setup(eurusd(), "BUY", stops, "BULLISH", "BULLISH", "BULLISH")
        assert verdict.allowed, f"ATR {step * 1e-6:.6f}: {verdict.reason}"


def test_prices_sit_on_the_broker_grid() -> None:
    spec = eurusd()
    stops = plan_stops(flat_candles(60, half_range=0.00074), spec, "BUY")
    assert stops is not None
    assert stops.sl_price == round(stops.sl_price, spec.digits)
    assert stops.entry - stops.sl_price == pytest.approx(stops.sl_points * spec.point)
    assert stops.tp_price - stops.entry == pytest.approx(stops.tp_points * spec.point)
    assert stops.tp_points >= 2 * stops.sl_points


def test_sell_stops_mirror_from_bid() -> None:
    spec = eurusd()
    stops = plan_stops(flat_candles(60, half_range=0.00074), spec, "SELL")
    assert stops is not None
    assert stops.entry == spec.bid
    assert stops.sl_price > stops.entry > stops.tp_price


def test_commission_widens_take_profit_to_keep_net_reward() -> None:
    settings = make_settings(commission_per_lot=7.0)
    stops = plan_stops(flat_candles(60, half_range=0.00074), eurusd(), "BUY", commission_per_lot=7.0)
    assert stops is not None
    assert stops.tp_points == math.ceil(2 * (stops.sl_points + 7) + 7)
    verdict = RiskEngine(settings).check_setup(eurusd(), "BUY", stops, "BULLISH", "BULLISH", "BULLISH")
    assert verdict.allowed, verdict.reason


def test_gold_stops_use_pip_override() -> None:
    gold = SymbolSpec(
        name="XAUUSD", digits=3, point=0.001, bid=4144.582, ask=4144.662, pip_size=0.1,
        tick_value=0.1, tick_size=0.001,
    )
    stops = plan_stops(flat_candles(60, price=4144.0, half_range=6.19), gold, "BUY")
    assert stops is not None
    assert stops.sl_pips == pytest.approx(stops.sl_points / 100)
    assert 240 < stops.sl_pips < 250
