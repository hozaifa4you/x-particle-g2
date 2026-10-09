# X-Particle G2

Conservative AI forex trader. A LangGraph agent plans, a typed risk engine allows, and `mt5-wrapper` executes.

## Quick start

```bash
cp .env.example .env
uv sync
python main.py trade once --dry-run --symbols EURUSDm
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
- Stops from ATR x2, never below 10 pips or 3x spread. Minimum 1:2 reward.
- Margin level above 200%, daily loss kill switch at 3%, spread cap at 5 pips.
- No trading on off days, Friday after 14:00, or when timeframes disagree.

## Monitoring

```python
import json
rows = [json.loads(line) for line in open("logs/trade_history.jsonl")]
print([r for r in rows[-5:]])
```

```bash
python main.py backtest --symbol EURUSDm --timeframe H1 --count 500
```

## Checks

```bash
ruff check .
mypy src --strict
pytest -q
```

Go live only after paper runs show 70-90% rejections, 1-3 trades a day, and steady demo behavior.
