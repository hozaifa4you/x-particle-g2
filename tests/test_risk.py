from datetime import UTC, datetime

from src.config import Settings
from src.mt5_client.models import Account, SymbolSpec
from src.risk.engine import RiskEngine


def conservative() -> RiskEngine:
    return RiskEngine(Settings(risk_pct=1.0, max_trades_per_day=3, cooldown_min=60, min_rr=2.0))


def spec() -> SymbolSpec:
    return SymbolSpec(
        name="EURUSDm", digits=5, point=0.00001, bid=1.1000, ask=1.1002,
        volume_min=0.01, volume_max=5.0, volume_step=0.01,
        tick_value=1.0, tick_size=0.00001,
    )


def test_sizing_uses_tick_value() -> None:
    engine = conservative()
    volume = engine.size_volume(10_000, 0.0020, spec())
    assert 0.4 < volume < 0.6


def test_rejects_wide_spread() -> None:
    engine = conservative()
    wide = spec().model_copy(update={"ask": 1.1060})
    verdict = engine.check_setup(wide, "BUY", 20.0, 50.0, "BULLISH", "BULLISH", "BULLISH")
    assert not verdict.allowed


def test_rejects_poor_reward() -> None:
    engine = conservative()
    verdict = engine.check_setup(spec(), "BUY", 20.0, 20.0, "BULLISH", "BULLISH", "BULLISH")
    assert not verdict.allowed


def test_rejects_misaligned_timeframes() -> None:
    engine = conservative()
    verdict = engine.check_setup(spec(), "BUY", 20.0, 50.0, "BULLISH", "BEARISH", "BULLISH")
    assert not verdict.allowed


def test_account_and_timing_gates() -> None:
    engine = RiskEngine(Settings(min_margin_level=200.0, max_concurrent_positions=2))
    poor = Account(margin_level=120.0, trade_allowed=True)
    assert not engine.check_account(poor, 0).allowed
    now = datetime(2026, 1, 9, 15, 0, tzinfo=UTC)
    assert "Friday" in engine.check_timing(now, 0, None).reason
    weekend = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
    assert not engine.check_timing(weekend, 0, None).allowed
