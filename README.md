# X-Particle G2

Conservative AI forex trader. A LangGraph agent plans, a typed risk engine allows, and `mt5-wrapper` executes.

## Quick start

```bash
cp .env.example .env
uv sync
uv run python main.py once --dry-run --symbols EURUSD
```

Expect `TRADE DECISION: NO TRADE` most runs. That is the design: the agent waits for aligned H1/H4/D1 trends, sane spreads, and validated reward.

## How it is organized

- `main.py` — `typer` CLI with `once`, `loop`, and `backtest` commands. Nothing else touches the terminal directly.
- `src/config.py` — every setting validated by Pydantic. Copy `.env.example` to `.env` and fill it in.
- `src/mt5_client/` — the only place that imports `mt5_wrapper`. Exposes `MT5Client`, frozen models, and `mt5_session()`.
- `src/strategy/` — pure EMA/RSI/MACD/ATR/Bollinger plus ATR stop planning. No network calls.
- `src/risk/` — the 1% risk, 3 trades/day, 60-minute cooldown, spread, margin, and session gates.
- `src/agent/` — five LangGraph nodes (`health`, `analyze`, `validate`, `decide`, `execute`) with structured `EXECUTE | NO_TRADE` output.
- `src/tools/` — eight small tools the agent may call. The risk engine still has the final word.
- `src/journal/` — JSONL decision log used for cooldowns, daily counts, and review.
- `tests/` — sizing, gates, client retcodes, and offline runner behavior.

## Conservative rules enforced in code

- 1% risk per trade, at most 3 trades per day, 60 minutes apart, 2 positions max.
- Lots are floored to the broker step. If even the minimum lot would risk more than 1%, the trade is refused.
- Stops from ATR x2, never below 10 pips or 3x spread, planned in whole broker points.
- Minimum 1:2 reward net of `COMMISSION_PER_LOT`. Stops are measured from the fill side (ask for buys, bid for sells),
  so the spread is already paid.
- Margin level must stay above 200% after the new trade's margin is added.
- Daily loss kill switch at 3%: today's closed deals (trades only, not deposits) plus open P/L, against the
  day-start balance. The day starts at 00:00 UTC; on brokers whose server clock runs ahead of UTC the window
  starts earlier, which only makes the switch stricter.
- Spread cap at 5 pips. A pip is 10 points on 3/5-digit quotes, otherwise one point, unless `PIP_OVERRIDES`
  matches the symbol prefix (default `XAU=0.1`, so a $0.08 gold spread is 0.8 pips).
- A zero quote or zero tick value is a `NO_TRADE`, never a guess. Every symbol is selected into Market Watch at
  the start of a run so the terminal streams prices before validation.
- No trading on off days, Friday after 14:00, or when timeframes disagree.

## Monitoring

```python
import json
rows = [json.loads(line) for line in open("logs/trade_history.jsonl")]
print([r for r in rows[-5:]])
```

```bash
python main.py backtest --symbol EURUSD --timeframe H1 --count 500
```

## Checks

```bash
uv run ruff check .
uv run mypy src --strict
uv run pytest -q
```

Tests use a fake terminal and ignore `.env`, so they never touch a real account.

Go live only after paper runs show 70-90% rejections, 1-3 trades a day, and steady demo behavior.
