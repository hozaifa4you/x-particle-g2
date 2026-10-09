from ..mt5_client.models import Candle


def closes(candles: list[Candle]) -> list[float]:
    return [c.close for c in candles]


def ema(values: list[float], period: int) -> float | None:
    if len(values) < period or period <= 0:
        return None
    weight = 2.0 / (period + 1)
    current = sum(values[:period]) / period
    for price in values[period:]:
        current = price * weight + current * (1 - weight)
    return current


def rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) < period + 1:
        return None
    gains, losses = 0.0, 0.0
    for i in range(len(values) - period, len(values)):
        change = values[i] - values[i - 1]
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100.0 - 100.0 / (1 + rs)


def macd(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, float] | None:
    if len(values) < slow + signal:
        return None
    fast_line = _ema_series(values, fast)
    slow_line = _ema_series(values, slow)
    line = [f - s for f, s in zip(fast_line, slow_line, strict=True)]
    sig = _ema_series(line, signal)
    return {"macd": line[-1], "signal": sig[-1], "histogram": line[-1] - sig[-1]}


def atr(candles: list[Candle], period: int = 14) -> float | None:
    if len(candles) < period + 1:
        return None
    ranges: list[float] = []
    for i in range(1, len(candles)):
        high, low, prev = candles[i].high, candles[i].low, candles[i - 1].close
        ranges.append(max(high - low, abs(high - prev), abs(low - prev)))
    recent = ranges[-period:]
    return sum(recent) / len(recent)


def bollinger(values: list[float], period: int = 20, width: float = 2.0) -> dict[str, float] | None:
    if len(values) < period:
        return None
    window = values[-period:]
    mean = sum(window) / period
    variance = sum((v - mean) ** 2 for v in window) / period
    dev = variance**0.5
    upper, lower = mean + width * dev, mean - width * dev
    band = ((upper - lower) / mean * 100) if mean else 0.0
    return {"upper": upper, "middle": mean, "lower": lower, "bandwidth": band}


def support_resistance(candles: list[Candle], lookback: int = 20) -> dict[str, list[float]]:
    if len(candles) < lookback * 2 + 1:
        return {"support": [], "resistance": []}
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    res, sup = [], []
    for i in range(lookback, len(candles) - lookback):
        if highs[i] == max(highs[i - lookback : i + lookback + 1]):
            res.append(highs[i])
        if lows[i] == min(lows[i - lookback : i + lookback + 1]):
            sup.append(lows[i])
    return {"support": _cluster(sup), "resistance": _cluster(res)}


def trend_of(values: list[float]) -> str:
    fast = ema(values, 50)
    slow = ema(values, 200)
    if fast is None or slow is None:
        return "UNKNOWN"
    if fast > slow:
        return "BULLISH"
    if fast < slow:
        return "BEARISH"
    return "FLAT"


def _ema_series(values: list[float], period: int) -> list[float]:
    weight = 2.0 / (period + 1)
    out: list[float] = []
    current = sum(values[:period]) / period
    out.extend([current] * period)
    for price in values[period:]:
        current = price * weight + current * (1 - weight)
        out.append(current)
    return out


def _cluster(levels: list[float], tol: float = 0.0005) -> list[float]:
    if not levels:
        return []
    ordered = sorted(levels)
    groups: list[list[float]] = [[ordered[0]]]
    for level in ordered[1:]:
        if abs(level - groups[-1][-1]) <= tol:
            groups[-1].append(level)
        else:
            groups.append([level])
    return [sum(g) / len(g) for g in groups]
