from src.agent.prompt import build_system_prompt
from tests.helpers import make_settings


def test_prompt_states_the_configured_limits() -> None:
    # The prompt used to hardcode 1%/3 trades/60 min, so the LLM narrated limits that were not in force.
    active = make_settings(risk_pct=10.0, max_trades_per_day=5, cooldown_min=15, min_rr=2.5, min_sl_pips=20.0)
    text = build_system_prompt(["EURUSD"], active)
    for expected in ("10% per trade", "5 trades per day", "15 minutes apart", "1:2.5 reward", "tighter than 20 pips"):
        assert expected in text
    assert "1% per trade" not in text


def test_prompt_does_not_claim_a_news_filter() -> None:
    text = build_system_prompt(["EURUSD"], make_settings()).lower()
    assert "news window" not in text
    assert "never mention news" in text
