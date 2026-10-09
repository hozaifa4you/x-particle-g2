from typing import Any

from ..tools.trading_tools import Toolkit
from .prompt import build_system_prompt
from .state import AgentState, TradeDecision


def build_graph(toolkit: Toolkit, symbols: list[str], dry_run: bool) -> Any:
    from langgraph.graph import END, StateGraph

    def health(state: AgentState) -> dict[str, Any]:
        notes = list(state.get("notes", []))
        account = toolkit.get_account()
        notes.append(f"account: {account.reason}")
        return {"notes": notes, "extra": {"account_ok": account.can_trade}}

    def analyze(state: AgentState) -> dict[str, Any]:
        found: list[dict[str, Any]] = []
        notes = list(state.get("notes", []))
        for symbol in state.get("symbols", symbols):
            views = toolkit.get_indicators_mtf(symbol)
            by_tf = {v.timeframe: v.trend for v in views}
            if by_tf.get("H1") == "BULLISH" and set(by_tf.values()) == {"BULLISH"}:
                found.append({"symbol": symbol, "side": "BUY", **by_tf})
                notes.append(f"{symbol}: aligned long")
            elif by_tf.get("H1") == "BEARISH" and set(by_tf.values()) == {"BEARISH"}:
                found.append({"symbol": symbol, "side": "SELL", **by_tf})
                notes.append(f"{symbol}: aligned short")
            else:
                notes.append(f"{symbol}: no alignment {by_tf}")
        return {"candidates": found, "notes": notes}

    def validate(state: AgentState) -> dict[str, Any]:

        notes = list(state.get("notes", []))
        best: dict[str, Any] | None = None
        for item in state.get("candidates", []):
            candidate = toolkit.plan_trade(item["symbol"], item["side"])
            candidate.trend_h1 = item.get("H1", "UNKNOWN")
            candidate.trend_h4 = item.get("H4", "UNKNOWN")
            candidate.trend_d1 = item.get("D1", "UNKNOWN")
            check = toolkit.check_conditions(candidate.symbol)
            if not check.allowed:
                notes.append(f"{candidate.symbol}: {check.reason}")
                continue
            verdict = toolkit.validate_setup(candidate)
            if not verdict.allowed:
                notes.append(f"{candidate.symbol}: {verdict.reason}")
                continue
            best = candidate.model_dump()
            notes.append(f"{candidate.symbol}: setup passed")
            break
        return {"decision": best or {}, "notes": notes}

    def decide(state: AgentState) -> dict[str, Any]:
        from .state import TradeDecision

        notes = list(state.get("notes", []))
        picked = state.get("decision") or {}
        if not picked:
            choice = TradeDecision(
                action="NO_TRADE", reason="; ".join(notes[-4:]) or "No aligned setup", dry_run=dry_run
            )
        else:
            choice = TradeDecision(
                action="EXECUTE", symbol=picked["symbol"], side=picked["side"],
                volume=picked["volume"], sl_pips=picked["sl_pips"], tp_pips=picked["tp_pips"],
                reason="Multi-timeframe alignment with validated risk", dry_run=dry_run,
            )
        refined = _llm_refine(symbols, notes, choice)
        return {"decision": refined.model_dump(), "notes": notes}

    def execute(state: AgentState) -> dict[str, Any]:
        from .state import Candidate, TradeDecision

        notes = list(state.get("notes", []))
        choice = TradeDecision.model_validate(state.get("decision", {}))
        if choice.action == "EXECUTE" and not dry_run:
            candidate = Candidate(
                symbol=choice.symbol, side=choice.side, volume=choice.volume,
                sl_pips=choice.sl_pips, tp_pips=choice.tp_pips,
                sl_price=0.0, tp_price=0.0,
            )
            planned = toolkit.plan_trade(candidate.symbol, candidate.side)
            candidate.sl_price = planned.sl_price
            candidate.tp_price = planned.tp_price
            outcome = toolkit.place_order(candidate, dry_run=False)
            notes.append(outcome)
        toolkit.log_decision(choice.symbol, choice.action, choice.reason, dry_run)
        return {"notes": notes}

    builder = StateGraph(AgentState)
    builder.add_node("health", health)
    builder.add_node("analyze", analyze)
    builder.add_node("validate", validate)
    builder.add_node("decide", decide)
    builder.add_node("execute", execute)
    builder.set_entry_point("health")
    builder.add_edge("health", "analyze")
    builder.add_edge("analyze", "validate")
    builder.add_edge("validate", "decide")
    builder.add_edge("decide", "execute")
    builder.add_edge("execute", END)
    return builder.compile()


def _llm_refine(symbols: list[str], notes: list[str], fallback: TradeDecision) -> TradeDecision:
    from ..config import settings

    if not settings.openrouter_api_key:
        return fallback
    try:
        from typing import Literal

        from langchain_openrouter import ChatOpenRouter
        from pydantic import BaseModel, SecretStr

        class DecisionSchema(BaseModel):
            action: Literal["EXECUTE", "NO_TRADE"]
            reason: str

        llm = ChatOpenRouter(
            api_key=SecretStr(settings.openrouter_api_key),
            model=settings.openrouter_model,
            temperature=0,
        ).with_structured_output(DecisionSchema)
        prompt = build_system_prompt(symbols) + "\nNotes:\n" + "\n".join(notes[-12:])
        answer = llm.invoke(prompt)
        if isinstance(answer, dict):
            raw_action = answer.get("action", fallback.action)
            raw_reason = answer.get("reason", fallback.reason)
        else:
            raw_action = getattr(answer, "action", fallback.action)
            raw_reason = getattr(answer, "reason", fallback.reason)
        action = str(raw_action)
        reason = str(raw_reason)
        if action == "NO_TRADE":
            fallback.action = "NO_TRADE"
            fallback.reason = reason
        else:
            fallback.reason = f"{fallback.reason} | LLM: {reason}"
        return fallback
    except Exception:
        return fallback
