from typing import TYPE_CHECKING, Any

import structlog

from ..config import Settings
from ..mt5_client.errors import MT5Error
from .prompt import build_system_prompt
from .state import AgentState, Candidate, TradeDecision

if TYPE_CHECKING:
    # Runtime import would cycle: trading_tools imports agent.state, which loads this package.
    from ..tools.trading_tools import Toolkit

log = structlog.get_logger("x-particle")


def build_graph(toolkit: "Toolkit", symbols: list[str], dry_run: bool) -> Any:
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
        best: Candidate | None = None
        for item in state.get("candidates", []):
            symbol = item["symbol"]
            try:
                check = toolkit.check_conditions(symbol)
                if not check.allowed:
                    notes.append(f"{symbol}: {check.reason}")
                    continue
                candidate = toolkit.plan_trade(symbol, item["side"])
                verdict = toolkit.validate_setup(candidate)
            except MT5Error as exc:
                notes.append(f"{symbol}: {exc}")
                continue
            if not verdict.allowed:
                notes.append(f"{symbol}: {verdict.reason}")
                continue
            best = candidate
            notes.append(f"{symbol}: setup passed, {candidate.sizing_reason}")
            break
        return {"decision": best.model_dump() if best else {}, "notes": notes}

    def decide(state: AgentState) -> dict[str, Any]:
        notes = list(state.get("notes", []))
        picked = state.get("decision") or {}
        if not picked:
            choice = TradeDecision(
                action="NO_TRADE", reason="; ".join(notes) or "No aligned setup", dry_run=dry_run
            )
        else:
            candidate = Candidate.model_validate(picked)
            stops = candidate.stops
            if stops is None:
                raise ValueError(f"{candidate.symbol} passed validation without a stop plan")
            choice = TradeDecision(
                action="EXECUTE", symbol=candidate.symbol, side=candidate.side, volume=candidate.volume,
                sl_pips=stops.sl_pips, tp_pips=stops.tp_pips, sl_price=stops.sl_price, tp_price=stops.tp_price,
                reason=f"Multi-timeframe alignment with validated risk ({candidate.sizing_reason})",
                dry_run=dry_run,
            )
        refined = _llm_refine(toolkit.settings, symbols, notes, choice)
        return {"decision": refined.model_dump(), "notes": notes}

    def execute(state: AgentState) -> dict[str, Any]:
        notes = list(state.get("notes", []))
        choice = TradeDecision.model_validate(state.get("decision", {}))
        if choice.action == "EXECUTE":
            # Send the exact validated prices; re-planning here would detach the stop from the sized volume.
            choice.outcome = toolkit.place_order(choice, dry_run=dry_run)
            notes.append(choice.outcome)
        toolkit.log_decision(choice)
        return {"decision": choice.model_dump(), "notes": notes}

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


def _llm_refine(active: Settings, symbols: list[str], notes: list[str], fallback: TradeDecision) -> TradeDecision:
    if not active.openrouter_api_key:
        return fallback
    try:
        from typing import Literal

        from langchain_openrouter import ChatOpenRouter
        from pydantic import BaseModel, SecretStr

        class DecisionSchema(BaseModel):
            action: Literal["EXECUTE", "NO_TRADE"]
            reason: str

        # Meta's provider rejects forced tool_choice, which function_calling needs; json_schema avoids it.
        llm = ChatOpenRouter(
            api_key=SecretStr(active.openrouter_api_key),
            model=active.openrouter_model,
            temperature=0,
        ).with_structured_output(DecisionSchema, method="json_schema")
        prompt = build_system_prompt(symbols, active) + "\nNotes:\n" + "\n".join(notes)
        answer = llm.invoke(prompt)
    except Exception as exc:
        # The LLM only advises; the deterministic decision stands, but the failure must stay visible.
        log.warning("llm_refine_failed", error=type(exc).__name__, detail=str(exc)[:200])
        fallback.reason = f"{fallback.reason} | LLM skipped: {type(exc).__name__}"
        return fallback
    if isinstance(answer, dict):
        raw_action = answer.get("action", fallback.action)
        raw_reason = answer.get("reason", fallback.reason)
    else:
        raw_action = getattr(answer, "action", fallback.action)
        raw_reason = getattr(answer, "reason", fallback.reason)
    # The engine's reason always survives verbatim; LLM prose may paraphrase checks that never ran.
    if str(raw_action) == "NO_TRADE" and fallback.action == "EXECUTE":
        fallback.action = "NO_TRADE"
        fallback.reason = f"LLM veto: {raw_reason} | engine: {fallback.reason}"
    else:
        fallback.reason = f"{fallback.reason} | LLM: {raw_reason}"
    return fallback
