from datetime import UTC, datetime, timedelta

from src.mt5_client.models import Candle


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


def flat_candles(n: int, price: float = 1.1) -> list[Candle]:
    base = datetime(2026, 1, 5, tzinfo=UTC)
    return [
        Candle(
            time=base + timedelta(hours=i),
            open=price, high=price + 0.0005, low=price - 0.0005, close=price, tick_volume=50,
        )
        for i in range(n)
    ]
