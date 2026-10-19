from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from src.config import Settings
from src.mt5_client.enums import Retcode
from src.mt5_client.models import Candle


def make_settings(**overrides: Any) -> Settings:
    # Skip .env so tests never pick up a real API key, terminal path, or login.
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def trend_candles(n: int, start: float = 1.0, step: float = 0.001) -> list[Candle]:
    base = datetime(2026, 1, 5, tzinfo=UTC)
    out: list[Candle] = []
    price = start
    for i in range(n):
        price += step
        out.append(
            Candle(
                time=base + timedelta(hours=i),
                open=price - step,
                high=price + 0.001,
                low=price - 0.002,
                close=price,
                tick_volume=100,
            )
        )
    return out


def flat_candles(n: int, price: float = 1.1, half_range: float = 0.0005) -> list[Candle]:
    base = datetime(2026, 1, 5, tzinfo=UTC)
    return [
        Candle(
            time=base + timedelta(hours=i),
            open=price, high=price + half_range, low=price - half_range, close=price, tick_volume=50,
        )
        for i in range(n)
    ]


def as_rows(candles: list[Candle]) -> list[dict[str, Any]]:
    return [
        {
            "time": int(c.time.timestamp()), "open": c.open, "high": c.high,
            "low": c.low, "close": c.close, "tick_volume": c.tick_volume,
        }
        for c in candles
    ]


def deal(kind: int, profit: float = 0.0, commission: float = 0.0, swap: float = 0.0) -> SimpleNamespace:
    data = {"type": kind, "profit": profit, "commission": commission, "swap": swap, "fee": 0.0}
    return SimpleNamespace(_asdict=lambda: data)


class FakeBackend:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.filling_mode = 2
        self.connect_ok = True
        self.select_ok = True
        self.send_retcode = int(Retcode.DONE)
        self.margin: float | None = 100.0
        self.rates: list[dict[str, Any]] | None = None
        self.deals: list[SimpleNamespace] | None = []
        self.tick: dict[str, Any] = {"bid": 1.1, "ask": 1.1002, "last": 1.1001, "time": 1_700_000_000}
        self.info: dict[str, Any] = {
            "digits": 5, "point": 0.00001, "visible": True,
            "volume_min": 0.01, "volume_max": 5.0, "volume_step": 0.01,
            "trade_stops_level": 10, "trade_tick_value": 1.0, "trade_tick_size": 0.00001,
        }
        self.account: dict[str, Any] = {
            "login": 1, "balance": 10000.0, "equity": 10000.0, "margin": 100.0,
            "margin_free": 9900.0, "margin_level": 500.0, "profit": 0.0,
            "currency": "USD", "server": "Demo", "leverage": 100, "trade_allowed": True,
        }

    def initialize(self, **kwargs: object) -> bool:
        return self.connect_ok

    def shutdown(self) -> None:
        pass

    def last_error(self) -> object:
        return (1, "ok")

    def account_info(self) -> object:
        return SimpleNamespace(_asdict=lambda: dict(self.account))

    def terminal_info(self) -> object:
        return SimpleNamespace(connected=True)

    def symbol_info(self, symbol: str) -> object:
        data = {"name": symbol, "filling_mode": self.filling_mode, **self.info}
        return SimpleNamespace(_asdict=lambda: data)

    def symbol_info_tick(self, symbol: str) -> object:
        return SimpleNamespace(_asdict=lambda: dict(self.tick))

    def symbol_select(self, symbol: str, enable: bool) -> bool:
        return self.select_ok

    def copy_rates_from_pos(self, symbol: str, timeframe: int, start: int, count: int) -> object:
        return self.rates

    def order_check(self, request: dict[str, Any]) -> object:
        return SimpleNamespace(retcode=0, comment="ok")

    def order_send(self, request: dict[str, Any]) -> object:
        self.sent.append(request)
        data = {"deal": 1, "order": 2, "price": request["price"], "comment": "done"}
        return SimpleNamespace(retcode=self.send_retcode, comment="done", _asdict=lambda: data)

    def positions_get(self, *args: object, **kwargs: object) -> object:
        return []

    def order_calc_margin(self, *args: object) -> object:
        return self.margin

    def history_deals_get(self, date_from: int, date_to: int) -> object:
        return self.deals

    def login(self, *args: object, **kwargs: object) -> bool:
        return True
