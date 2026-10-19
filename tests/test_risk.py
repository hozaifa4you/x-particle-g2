from datetime import UTC, datetime

from src.mt5_client.models import Account, SymbolSpec
from src.risk.engine import RiskEngine
from src.strategy.stops import StopPlan
from tests.helpers import make_settings


def conservative(**overrides: object) -> RiskEngine:
    return RiskEngine(make_settings(risk_pct=1.0, max_trades_per_day=3, cooldown_min=60, min_rr=2.0, **overrides))


def spec(**overrides: object) -> SymbolSpec:
    base = SymbolSpec(
        name="EURUSD", digits=5, point=0.00001, bid=1.1000, ask=1.1002,
        volume_min=0.01, volume_max=5.0, volume_step=0.01,
        tick_value=1.0, tick_size=0.00001,
    )
    return base.model_copy(update=overrides)


def plan(sl_points: int = 200, tp_points: int = 500) -> StopPlan:
    return StopPlan(sl_points=sl_points, tp_points=tp_points, sl_pips=sl_points / 10, tp_pips=tp_points / 10)


def account(**overrides: object) -> Account:
    return Account(balance=500.0, equity=500.0, trade_allowed=True).model_copy(update=overrides)


def test_sizing_uses_tick_value() -> None:
    sized = conservative().size_volume(10_000, 0.0020, spec())
    assert sized.allowed and sized.volume == 0.5


def test_sizing_floors_instead_of_rounding_up() -> None:
    # Live EURUSD on a $500 demo: raw 0.0169 lots used to round up to 0.02 (1.18% risk).
    sized = conservative().size_volume(500, 0.00296, spec())
    assert sized.allowed and sized.volume == 0.01
    assert sized.volume * 296 * 1.0 <= 500 * 0.01


def test_sizing_refuses_when_minimum_lot_breaks_risk() -> None:
    # Live XAUUSD on a $500 demo: the 0.01 minimum lot would have risked 4.95%.
    gold = spec(name="XAUUSD", digits=3, point=0.001, tick_value=0.1, tick_size=0.001)
    sized = conservative().size_volume(500, 24.763, gold)
    assert not sized.allowed and sized.volume == 0.0
    assert "4.95%" in sized.reason


def test_sizing_refuses_missing_contract_data() -> None:
    sized = conservative().size_volume(500, 0.002, spec(tick_value=0.0))
    assert not sized.allowed and sized.volume == 0.0


def test_sizing_includes_commission() -> None:
    sized = conservative(commission_per_lot=7.0).size_volume(10_000, 0.0020, spec())
    assert sized.allowed and sized.volume == 0.48


def test_daily_loss_counts_closed_trades() -> None:
    engine = conservative(max_daily_loss_pct=3.0)
    closed_loss = account(balance=485.0, equity=485.0, profit=0.0)
    assert "Daily loss" in engine.check_account(closed_loss, 0, closed_pnl_today=-15.0).reason
    assert engine.check_account(account(balance=486.0, equity=486.0), 0, closed_pnl_today=-14.0).allowed


def test_daily_loss_counts_open_and_closed_together() -> None:
    engine = conservative(max_daily_loss_pct=3.0)
    mixed = account(balance=492.0, equity=485.0, profit=-7.0)
    assert not engine.check_account(mixed, 1, closed_pnl_today=-8.0).allowed


def test_margin_is_checked_after_the_new_trade() -> None:
    engine = conservative(min_margin_level=200.0)
    assert not engine.check_margin(account(margin=0.0), required_margin=300.0).allowed
    assert engine.check_margin(account(margin=0.0), required_margin=100.0).allowed


def test_rejects_wide_spread() -> None:
    verdict = conservative().check_setup(spec(ask=1.1060), "BUY", plan(), "BULLISH", "BULLISH", "BULLISH")
    assert not verdict.allowed


def test_rejects_poor_reward() -> None:
    verdict = conservative().check_setup(spec(), "BUY", plan(200, 200), "BULLISH", "BULLISH", "BULLISH")
    assert not verdict.allowed


def test_exact_minimum_reward_passes() -> None:
    verdict = conservative().check_setup(spec(), "BUY", plan(296, 592), "BULLISH", "BULLISH", "BULLISH")
    assert verdict.allowed, verdict.reason


def test_reward_is_net_of_commission() -> None:
    verdict = conservative(commission_per_lot=7.0).check_setup(
        spec(), "BUY", plan(200, 400), "BULLISH", "BULLISH", "BULLISH"
    )
    assert not verdict.allowed and "Net reward" in verdict.reason


def test_rejects_misaligned_timeframes() -> None:
    verdict = conservative().check_setup(spec(), "BUY", plan(), "BULLISH", "BEARISH", "BULLISH")
    assert not verdict.allowed


def test_account_and_timing_gates() -> None:
    engine = RiskEngine(make_settings(min_margin_level=200.0, max_concurrent_positions=2))
    poor = Account(balance=1000.0, margin_level=120.0, trade_allowed=True)
    assert not engine.check_account(poor, 0, closed_pnl_today=0.0).allowed
    now = datetime(2026, 1, 9, 15, 0, tzinfo=UTC)
    assert "Friday" in engine.check_timing(now, 0, None).reason
    weekend = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
    assert not engine.check_timing(weekend, 0, None).allowed
