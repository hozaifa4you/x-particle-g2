from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from src.mt5_client.client import MT5Client
from src.mt5_client.enums import DealType, OrderSide, Retcode, Timeframe
from src.mt5_client.errors import MT5Error
from src.mt5_client.models import MarketOrderRequest
from tests.helpers import FakeBackend, deal, make_settings

DAY_START = datetime(2026, 1, 7, tzinfo=UTC)


def client(backend: FakeBackend | None = None, **overrides: object) -> MT5Client:
    handle = MT5Client(make_settings(dry_run=True, **overrides), backend=backend or FakeBackend())  # type: ignore[arg-type]
    handle.connect()
    return handle


def gold_backend() -> FakeBackend:
    backend = FakeBackend()
    backend.info.update({"digits": 3, "point": 0.001, "trade_tick_value": 0.1, "trade_tick_size": 0.001})
    backend.tick.update({"bid": 4144.582, "ask": 4144.662})
    return backend


def test_empty_rates_become_empty_list() -> None:
    assert client().candles("EURUSD", Timeframe.H1) == []


def test_send_market_floors_volume_and_sends() -> None:
    backend = FakeBackend()
    handle = client(backend)
    result = handle.send_market(
        MarketOrderRequest(symbol="EURUSD", side="BUY", volume=0.339, sl_price=1.098, tp_price=1.104),
        handle.symbol("EURUSD"),
    )
    assert result.ok and result.retcode == int(Retcode.DONE)
    assert backend.sent[0]["volume"] == 0.33


def test_rejected_check_raises() -> None:
    handle = client()

    def bad_check(request: dict) -> object:
        return SimpleNamespace(retcode=int(Retcode.INVALID_STOPS), comment="invalid stops")

    handle._backend.order_check = bad_check  # type: ignore[method-assign]
    with pytest.raises(MT5Error, match="order_check"):
        handle.send_market(MarketOrderRequest(symbol="EURUSD", side="BUY", volume=0.1), handle.symbol("EURUSD"))


@pytest.mark.parametrize("code", [Retcode.DONE, Retcode.PLACED, Retcode.DONE_PARTIAL])
def test_accepted_retcodes_return_ok(code: Retcode) -> None:
    backend = FakeBackend()
    backend.send_retcode = int(code)
    handle = client(backend)
    result = handle.send_market(MarketOrderRequest(symbol="EURUSD", side="SELL", volume=0.1), handle.symbol("EURUSD"))
    assert result.ok and result.retcode == int(code)


@pytest.mark.parametrize(
    "code", [Retcode.INVALID_STOPS, Retcode.MARKET_CLOSED, Retcode.NO_MONEY, Retcode.CLIENT_DISABLES_AT]
)
def test_failed_retcodes_raise_with_context(code: Retcode) -> None:
    backend = FakeBackend()
    backend.send_retcode = int(code)
    handle = client(backend)
    with pytest.raises(MT5Error) as caught:
        handle.send_market(MarketOrderRequest(symbol="EURUSD", side="BUY", volume=0.1), handle.symbol("EURUSD"))
    assert caught.value.retcode == int(code)


def test_zero_quote_is_rejected() -> None:
    # Live terminals return 0/0 for a symbol until Market Watch starts streaming it.
    backend = FakeBackend()
    backend.tick.update({"bid": 0.0, "ask": 0.0, "time": 0})
    with pytest.raises(MT5Error, match="No live quote"):
        client(backend).symbol("GBPUSD")


def test_zero_tick_value_is_rejected() -> None:
    backend = FakeBackend()
    backend.info["trade_tick_value"] = 0.0
    with pytest.raises(MT5Error, match="No tick value"):
        client(backend).symbol("USDCHF")


def test_gold_uses_pip_override() -> None:
    spec = client(gold_backend()).symbol("XAUUSD")
    assert spec.pip() == 0.1
    assert spec.spread_pips() == pytest.approx(0.8)


def test_gold_without_override_counts_points_as_pips() -> None:
    spec = client(gold_backend(), pip_overrides="").symbol("XAUUSD")
    assert spec.pip() == pytest.approx(0.01)
    assert spec.spread_pips() == pytest.approx(8.0)


def test_closed_pnl_counts_trades_but_not_deposits() -> None:
    backend = FakeBackend()
    backend.deals = [
        deal(DealType.BALANCE, profit=500.0),
        deal(DealType.BUY, commission=-0.7),
        deal(DealType.SELL, profit=-12.5, commission=-0.7, swap=-0.1),
    ]
    assert client(backend).closed_pnl_since(DAY_START) == pytest.approx(-14.0)


def test_closed_pnl_unavailable_raises() -> None:
    backend = FakeBackend()
    backend.deals = None
    with pytest.raises(MT5Error, match="history_deals_get"):
        client(backend).closed_pnl_since(DAY_START)


def test_normalize_volume_floors_and_rejects_below_minimum() -> None:
    handle = client()
    spec = handle.symbol("EURUSD")
    assert handle.normalize_volume(spec, 0.0169) == 0.01
    assert handle.normalize_volume(spec, 0.29) == 0.29
    with pytest.raises(MT5Error, match="below"):
        handle.normalize_volume(spec, 0.009)


def test_missing_margin_raises() -> None:
    backend = FakeBackend()
    backend.margin = None
    with pytest.raises(MT5Error, match="margin"):
        client(backend).margin_for("EURUSD", OrderSide.BUY, 0.1, 1.1)


def test_watch_rejects_unknown_symbol() -> None:
    backend = FakeBackend()
    backend.select_ok = False
    with pytest.raises(MT5Error, match="Cannot select"):
        client(backend).watch(["EURUSD"])
