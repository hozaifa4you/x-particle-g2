# Agent Instructions

This file governs all code and agent work in x-particle-g2. Follow it on every change.

## How to write code here

- Write code that reads naturally. Prefer small functions with clear names over clever constructs.
- Keep modules focused on one responsibility. If a file grows past ~250 lines, split it.
- Reuse through composition. New behavior goes in a shared helper, not a copy-paste variant.
- Use standard library and declared dependencies first. Do not add a dependency for something trivial.
- Type everything at boundaries. Public functions carry annotations and Pydantic models where data crosses layers.
- Return values, don't print. Only `main.py` and the journal may touch stdout, files, or the network directly.
- Fail loudly with context. Raise `MT5Error` or `ValueError` with what happened and what was expected. Never swallow exceptions or return magic strings.
- Keep comments sparse. Name things well so the code explains itself. Comment only the non-obvious why, never the what.

## What good looks like

- A reader can follow any flow without jumping between more than three files.
- Pure calculations live apart from MT5, LLM, and filesystem calls, so they are testable without credentials.
- `mt5_wrapper` is imported in exactly one place: `src/mt5_client/client.py`. Everything else uses `MT5Client`.
- Risk rules are enforced in `src/risk/engine.py`, not in prompt text. The agent can suggest, only the engine allows.
- Every trade decision is explainable from the journal entry alone.

## What to avoid

- No secrets in code, logs, or stdout. No `print(API_KEY)`, no hardcoded logins.
- No bare `dict`, `Any`, or `Optional[str]` error returns at module boundaries. Use models and result types.
- No magic numbers inline. Risk limits, pips, timeouts come from `src/config.py`.
- No dead code, no commented-out blocks, no placeholder `TODO` without a test that pins the gap.
- No AI-looking filler: banner comments, excessive section dividers, echoing the obvious, or over-documented trivial getters.

## Patterns to use

- Pydantic frozen models for data, `IntEnum` for MT5 constants, `Result`-style returns (`ok` / error) for fallible calls.
- Context managers for sessions (`mt5_session`), dependency injection for the terminal backend so tests run without MT5.
- `typer` for the CLI, `structlog` for logging, `pytest` for behavior, `ruff` + `mypy --strict` before every commit.
- One LangGraph node per phase, eight tools maximum, structured `TradeDecision` output. Default to `NO_TRADE`.

## Before finishing

- Run `ruff check .`, `mypy src --strict`, and `pytest -q`. Fix what they report instead of silencing it.
- Run the paper path once: `python main.py trade once --dry-run`. Confirm a typed decision and a journal entry, no live order.
- Update `README.md` and `.env.example` when you change settings or flows.
