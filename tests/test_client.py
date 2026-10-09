from types import SimpleNamespace

from src.config import Settings
from src.mt5_client.client import MT5Client
from src.mt5_client.enums import Retcode
from src.mt5_client.errors import MT5Error
from src.mt5_client.models import MarketOrderRequest


class FakeBackend:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.filling_mode = 2

    def initialize(self, **kwargs: object) -> bool:
        return True

    def shutdown(self) -> None:
        pass

    def last_error(self) -> object:
        return (1, "ok")

    def account_info(self) -> object:
        return SimpleNamespace(
            _asdict=lambda: {
                "login": 1, "balance": 10000.0, "equity": 10000.0, "margin": 100.0,
                "margin_free": 9900.0, "margin_level": 500.0, "profit": 0.0,
                "currency": "USD", "server": "Demo", "leverage": 100, "trade_allowed": True,
            }
        )

    def terminal_info(self) -> object:
        return SimpleNamespace(connected=True)

    def symbol_info(self, symbol: str) -> object:
        return SimpleNamespace(
            _asdict=lambda: {
                "name": symbol, "digits": 5, "point": 0.00001, "visible": True,
                "volume_min": 0.01, "volume_max": 5.0, "volume_step": 0.01,
                "trade_stops_level": 10, "trade_tick_value": 1.0,
                "trade_tick_size": 0.00001, "filling_mode": self.filling_mode,
            }
        )

    def symbol_info_tick(self, symbol: str) -> object:
        return SimpleNamespace(_asdict=lambda: {"bid": 1.1, "ask": 1.1002, "last": 1.1001, "time": 1_700_000_000})

    def symbol_select(self, symbol: str, enable: bool) -> bool:
        return True

    def copy_rates_from_pos(self, symbol: str, timeframe: int, start: int, count: int) -> object:
        return None

    def order_check(self, request: dict) -> object:
        return SimpleNamespace(retcode=0, comment="ok")

    def order_send(self, request: dict) -> object:
        self.sent.append(request)
        return SimpleNamespace(
            retcode=int(Retcode.DONE), deal=1, order=2, price=request["price"],
            bid=1.1, ask=1.1002, comment="done", request_id=7,
            _asdict=lambda: {"deal": 1, "order": 2, "price": request["price"], "comment": "done"},
        )

    def positions_get(self, *args: object, **kwargs: object) -> object:
        return []

    def order_calc_margin(self, *args: object) -> object:
        return 100.0

    def login(self, *args: object, **kwargs: object) -> bool:
        return True


def client() -> MT5Client:
    active = Settings(dry_run=True)
    handle = MT5Client(active, backend=FakeBackend())  # type: ignore[arg-type]
    handle.connect()
    return handle


def test_empty_rates_become_empty_list() -> None:
    assert client().candles("EURUSDm", __import__("src.mt5_client.enums", fromlist=["Timeframe"]).Timeframe.H1) == []


def test_send_market_normalizes_and_sends() -> None:
    handle = client()
    spec = handle.symbol("EURUSDm")
    result = handle.send_market(
        MarketOrderRequest(symbol="EURUSDm", side="BUY", volume=0.333, sl_price=1.098, tp_price=1.104),
        spec,
    )
    assert result.ok and result.retcode == int(Retcode.DONE)


def test_rejected_check_raises() -> None:
    handle = client()

    def bad_check(request: dict) -> object:
        return SimpleNamespace(retcode=10016, comment="invalid stops")

    handle._backend.order_check = bad_check  # type: ignore[attr-defined]
    spec = handle.symbol("EURUSDm")
    try:
        handle.send_market(MarketOrderRequest(symbol="EURUSDm", side="BUY", volume=0.1), spec)
    except MT5Error as exc:
        assert "order_check" in str(exc)
    else:
        raise AssertionError("expected MT5Error")
