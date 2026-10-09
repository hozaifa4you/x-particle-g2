from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openrouter_api_key: str = ""
    openrouter_model: str = "meta/muse-spark-1.3-contributor"
    tavily_api_key: str = ""

    mt5_login: str = ""
    mt5_password: str = ""
    mt5_server: str = ""
    mt5_path: str = ""
    mt5_timeout_ms: int = 60000

    symbols: str = "EURUSDm,GBPUSDm,USDJPYm,XAUUSDm,AUDUSDm,USDCADm,USDCHFm,NZDUSDm"
    timeframes: str = "H1,H4,D1"
    magic_number: int = 240910
    dry_run: bool = True

    risk_pct: float = 1.0
    max_trades_per_day: int = 3
    cooldown_min: int = 60
    min_rr: float = 2.0
    max_concurrent_positions: int = 2
    min_margin_level: float = 200.0
    max_daily_loss_pct: float = 3.0
    max_spread_pips: float = 5.0
    min_sl_pips: float = 10.0
    atr_mult: float = 2.0
    off_days: str = "Saturday,Sunday"
    friday_cutoff_hour: int = 14

    journal_path: str = "logs/trade_history.jsonl"
    log_level: str = "INFO"

    @property
    def symbol_list(self) -> list[str]:
        return [s.strip() for s in self.symbols.split(",") if s.strip()]

    @property
    def timeframe_list(self) -> list[str]:
        return [t.strip().upper() for t in self.timeframes.split(",") if t.strip()]

    @property
    def off_day_list(self) -> list[str]:
        return [d.strip() for d in self.off_days.split(",") if d.strip()]


settings = Settings()
