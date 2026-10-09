from src.strategy import indicators
from tests.helpers import flat_candles, trend_candles


def test_trend_detection() -> None:
    assert indicators.trend_of(indicators.closes(trend_candles(250))) == "BULLISH"


def test_rsi_bounds() -> None:
    value = indicators.rsi(indicators.closes(trend_candles(60)))
    assert value is not None and 0 <= value <= 100


def test_atr_positive() -> None:
    assert (indicators.atr(trend_candles(60)) or 0) > 0


def test_warmup_guards() -> None:
    short = indicators.closes(flat_candles(10))
    assert indicators.ema(short, 50) is None
    assert indicators.macd(short) is None


def test_bollinger_shape() -> None:
    bands = indicators.bollinger(indicators.closes(trend_candles(60)))
    assert bands is not None and bands["upper"] > bands["middle"] > bands["lower"]
