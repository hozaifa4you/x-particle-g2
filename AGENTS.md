# X-Particle G2 — Agent Instructions

Read this file before any code, trade-logic, or docs change. It is the source of truth for how this repo works and how you must behave in it.

## 1. What this project is

Conservative AI forex trader. A LangGraph agent proposes, a typed risk engine disposes, and `mt5-wrapper` executes against a MetaTrader 5 terminal.

Flow: `main.py` (typer CLI) loads `src/config.py` (pydantic-settings), opens `mt5_session()`, runs the five-node graph (`health → analyze → validate → decide → execute`), and appends every outcome to the JSONL journal. Paper mode is the default. Live orders only happen with `DRY_RUN=false` plus a passing gate.

## 2. Model policy

- Default agent model is `meta/muse-spark-1.3-contributor` via OpenRouter (`OPENROUTER_MODEL`). Keep it until Meta ships a newer model, then update `src/config.py`, `.env.example`, and this section together.
- Temperature is 0 everywhere. The model refines reasons; it never bypasses `RiskEngine`.
- If `OPENROUTER_API_KEY` is empty, the runner must still work: deterministic rules produce the decision, journal entry included. Never fail a run just because the LLM is unreachable.

## 3. Anti-hallucination rules

- Never invent indicator values, prices, spreads, margins, or retcodes. Read them from `MT5Client`, `analyze_symbol()`, or `plan_stops()`. If data is missing, return `NO_TRADE` with the exact gap as the reason.
- Never invent tool names, file paths, env vars, or MT5 constants. If you reference one, it must exist in this repo or in `mt5_wrapper`. Check with Glob/Grep before writing.
- Never claim a trade was placed unless `send_market()` returned `OrderResult(ok=True)`. Paper runs must say `paper: order not sent`.
- Never present prompt text as enforcement. Only `src/risk/engine.py` gates trading. The system prompt advises; the engine decides.
- When uncertain, say what is unknown, what you checked, and what would resolve it. Do not fill gaps with plausible-sounding defaults.

## 4. Architecture and file map

- `main.py` — CLI only (`once`, `loop`, `backtest`). No trading math here.
- `src/config.py` — all tunables. No magic numbers elsewhere; read limits from `Settings`.
- `src/mt5_client/` — the only layer that imports `mt5_wrapper`. Exposes `MT5Client`, `mt5_session()`, frozen Pydantic models, `IntEnum` constants, `MT5Error`, and `rows_to_candles()` (numpy void → `list[Candle]`, empty → `[]`).
- `src/strategy/` — pure functions on `list[Candle]`: EMA, RSI, MACD, ATR, Bollinger, support/resistance, `plan_stops()`. No network, no filesystem.
- `src/risk/` — `RiskEngine` (`size_volume`, `check_account`, `check_timing`, `check_setup`) plus session helpers. Tick-value sizing, spread-adjusted reward, margin/drawdown/cooldown/session gates.
- `src/tools/trading_tools.py` — `Toolkit` plus at most eight LangChain `StructuredTool`s. Tools report; they do not authorize.
- `src/agent/` — `state.py` (`TradeDecision`, `AgentState`), `prompt.py` (`build_system_prompt()`), `graph.py` (five nodes), `runner.py` (`run_once()` with offline `NO_TRADE` fallback).
- `src/journal/store.py` — JSONL append, `today_entries()`, `last_trade_time()`. The sole source for daily counts and cooldowns.
- `src/backtest/engine.py` — needs a live terminal; reports trend/RSI/ATR without placing orders.
- `tests/` — behavior pins for sizing, gates, retcodes, journal, and offline runner.

## 5. Conservative risk rules (enforced in code)

1% per trade, 3 trades/day, 60 minutes apart, 2 positions max, 1:2 minimum reward, ATR×2 stops floored at 10 pips and 3× spread, 5-pip spread cap, 200% margin floor, 3% daily-loss kill switch, no off-day or post-14:00 Friday trading, H1/H4/D1 must agree. Changing any number means updating `src/config.py`, `.env.example`, `README.md`, and the tests that pin it.

## 6. How to write code here

- Small focused modules; split past ~250 lines. Compose helpers instead of duplicating logic.
- Type all boundaries. Frozen Pydantic models for data, `IntEnum` for MT5 constants, `MT5Error` with retcode context for failures. No bare `dict`/`Any` returns, no magic strings for errors.
- Keep `mt5_wrapper` inside `src/mt5_client/client.py`. Keep calculations away from I/O so tests run without a terminal or API key. Inject a fake backend via the `TerminalBackend` protocol.
- Human-readable names, standard patterns (`typer`, `structlog`, `pytest`, context managers, dependency injection). Sparse comments: explain the non-obvious why, never restate the what. No banners, no filler, no dead code, no commented-out blocks.

## 7. What to avoid

- No secrets in code, logs, stdout, or examples. No `print(API_KEY)`, no real logins in `.env.example`.
- No new dependency without using it in code and recording why in the commit message.
- No silent failures, no swallowed exceptions, no `TODO` without a failing test that defines done.
- No prompt-only risk changes. If the engine does not enforce it, it is not a rule.

## 8. Workflows

- Adding a tool: extend `Toolkit` with a typed method, expose it in `langchain_tools()` only if the eight-tool budget allows, add a test, update `README.md`.
- Changing risk: update engine + settings + example env + tests + README in the same commit.
- Touching MT5 mapping: update `enums.py`/`models.py`/`client.py` together and cover retcodes `DONE`, `PLACED`, `DONE_PARTIAL`, `INVALID_STOPS`, `MARKET_CLOSED`, `NO_MONEY`, `CLIENT_DISABLES_AT` in `tests/test_client.py`.

## 9. Before finishing

Run in order and fix instead of silencing: `uv run ruff check .`, `uv run mypy src --strict`, `uv run pytest -q`. Then paper-run `uv run python main.py once --dry-run --symbols EURUSDm` and confirm a typed decision plus a journal entry with no live order. Update `README.md` and `.env.example` whenever settings or flows change.
