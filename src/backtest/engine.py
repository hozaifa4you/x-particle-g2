from ..config import settings
from ..mt5_client.client import mt5_session
from ..mt5_client.enums import NAME_TO_TIMEFRAME
from ..strategy.stops import analyze_symbol


def summarize(symbol: str = "EURUSDm", timeframe: str = "H1", count: int = 500) -> str:
    frame = NAME_TO_TIMEFRAME.get(timeframe.upper())
    if frame is None:
        return f"Unknown timeframe {timeframe}"
    try:
        with mt5_session(settings) as client:
            candles = client.candles(symbol, frame, count)
    except Exception as exc:
        return f"Backtest needs a live MT5 terminal: {exc}"
    if len(candles) < 210:
        return f"Not enough bars for {symbol} {timeframe}: {len(candles)}"
    view = analyze_symbol(candles)
    wins = sum(1 for c in candles[-100:] if c.close > c.open)
    return (
        f"Backtest {symbol} {timeframe} bars={len(candles)} "
        f"trend={view['trend']} rsi={view['rsi']:.1f} atr={view['atr']:.5f} "
        f"last100 up={wins}/100. Live paper trading still required before real orders."
    )
