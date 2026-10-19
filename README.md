# X-Particle G2

Conservative AI forex trader. A LangGraph agent plans, a typed risk engine allows, and `mt5-wrapper` executes.

## Requirements

- Windows. `mt5-wrapper` imports the `MetaTrader5` package, which only runs on Windows.
- A MetaTrader 5 terminal installed and logged in to your broker account. Start on a demo account.
- Python 3.13 and [uv](https://docs.astral.sh/uv/).
- Optional: an OpenRouter API key. Without one, the deterministic rules make every decision on their own.

## Setup

```powershell
uv sync --extra dev
Copy-Item .env.example .env
```

`--extra dev` installs ruff, mypy, and pytest for the checks below. Then edit `.env`:

| Setting | What to put there |
|---|---|
| `MT5_PATH` | Full path to your terminal's `terminal64.exe`. The terminal is started if it is not running. |
| `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER` | Leave all three empty to use the account already logged in to the terminal, or fill all three. |
| `SYMBOLS` | Exact names from your broker's Market Watch. Exness Standard uses `EURUSDm`; Raw Spread uses `EURUSD`. |
| `DRY_RUN` | `true` (default) = paper mode, no orders sent. `false` = live: real orders to the logged-in account. |
| `COMMISSION_PER_LOT` | Round-turn commission per 1.0 lot. Exness Raw Spread charges up to 3.50 per side, so `7.0`. Use `0` on spread-only accounts. |
| `OPENROUTER_API_KEY` | Optional. When empty, runs skip the LLM step. |

Every other setting already has a conservative default; see [Conservative rules](#conservative-rules-enforced-in-code).

## Running it

`DRY_RUN` in `.env` decides the mode. `--dry-run` forces paper mode for one command even when `DRY_RUN=false`. No flag can force live mode: going live only happens by setting `DRY_RUN=false`. Every decision line shows the mode it ran in, `[PAPER]` or `[LIVE]`.

**One run.** Analyzes, validates, and journals the decision. In paper mode nothing is sent:

```powershell
uv run python main.py once --symbols EURUSD   # one symbol, mode from DRY_RUN
uv run python main.py once                    # every symbol in SYMBOLS
uv run python main.py once --dry-run          # paper, whatever DRY_RUN says
```

**Loop.** Repeats `once` every `--interval-min` minutes (5 to 240, default 30). Stop it with `Ctrl+C`:

```powershell
uv run python main.py loop --interval-min 30
uv run python main.py loop --dry-run          # paper loop while DRY_RUN=false
```

**Market snapshot.** Prints trend, RSI, ATR, and the number of up candles among the last 100 bars. It does not simulate trades:

```powershell
uv run python main.py backtest --symbol EURUSD --timeframe H1 --count 500
```

**Live trading.** Sends real orders to the logged-in account. Do this only after paper runs on a demo look steady. Before you start:

1. Turn on **Algo Trading** in the terminal. Otherwise MT5 rejects orders with retcode 10027 (`CLIENT_DISABLES_AT`).
2. Check which account the terminal is logged in to. Live mode trades whatever account that is.
3. Set `DRY_RUN=false` in `.env`, then use the same `once` or `loop` commands without `--dry-run`.

Live orders still pass every risk gate first. Set `DRY_RUN=true` again to stop sending orders.

### Reading the output

Expect `TRADE DECISION: NO TRADE [PAPER]` (or `[LIVE]`) on most runs. That is by design: the agent waits until every timeframe in `TIMEFRAMES` (H1/H4/D1 by default) points the same way, the spread is sane, and the reward is validated. The reason line says which check stopped it.

When a setup passes, you get `TRADE DECISION: EXECUTE` with symbol, direction, volume, stop and take in pips and price, and an `Outcome:` line:

- `paper: order not sent` in paper mode.
- `order sent: order=… deal=… price=…` only when MT5 confirmed the order.

Each run appends one JSON line to `logs/trade_history.jsonl`.

### Common messages

| Message | Meaning |
|---|---|
| `MT5 unavailable: MT5 initialize failed` | The terminal could not be reached. Check `MT5_PATH` and that the terminal opens. Run again on a transient `IPC send failed`. |
| `Cannot select symbol X` | `X` is not in your broker's symbol list. Usually a suffix mismatch in `SYMBOLS`. |
| `No live quote for X` | No price yet: the market is closed, or the symbol was just added to Market Watch. The next run picks it up. |
| `Min lot 0.01 risks N%, above the 1.0% limit` | The account is too small for that symbol's stop. Gold on a $500 account always shows this. |
| `Market closed for off day` / `Friday cutoff passed` | Session rules; no trading on weekends or after 14:00 UTC on Friday. |
| `LLM skipped: <error>` | OpenRouter failed. The rules still made the decision, and the error is in the log. |

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

Show the last five decisions:

```powershell
Get-Content logs/trade_history.jsonl -Tail 5
```

The journal is also the source for the daily trade count and the cooldown, so do not edit or delete it while trading.

## Checks

```powershell
uv run ruff check .
uv run mypy src --strict
uv run pytest -q
```

Tests use a fake terminal and ignore `.env`, so they never touch a real account.

Go live only after paper runs show 70-90% rejections, 1-3 trades a day, and steady demo behavior.
