from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from .models import Candle


def rows_to_candles(rows: Any) -> list[Candle]:
    if rows is None:
        return []
    if not isinstance(rows, Iterable):
        return []
    items = list(rows)
    if not items:
        return []
    out: list[Candle] = []
    for row in items:
        item = row_to_candle(row)
        if item is not None:
            out.append(item)
    return out


def row_to_candle(row: Any) -> Candle | None:
    if isinstance(row, dict):
        return Candle(
            time=epoch_to_utc(row.get("time", 0)),
            open=float(row.get("open", 0.0)),
            high=float(row.get("high", 0.0)),
            low=float(row.get("low", 0.0)),
            close=float(row.get("close", 0.0)),
            tick_volume=int(row.get("tick_volume", 0)),
        )
    as_dict = getattr(row, "_asdict", None)
    if callable(as_dict):
        return row_to_candle(as_dict())
    dtype = getattr(row, "dtype", None)
    names: Any = getattr(dtype, "names", None)
    if names:
        try:
            values = {name: row[i] for i, name in enumerate(names)}
            return row_to_candle(values)
        except Exception:
            return None
    return None


def epoch_to_utc(value: Any) -> datetime:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return datetime.now(UTC)
    return datetime.fromtimestamp(seconds, tz=UTC)
