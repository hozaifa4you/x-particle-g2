from datetime import datetime

from pydantic import BaseModel, Field


class Frozen(BaseModel):
    model_config = {"frozen": True}


class Account(Frozen):
    login: int = 0
    balance: float = 0.0
    equity: float = 0.0
    margin: float = 0.0
    margin_free: float = 0.0
    margin_level: float = 0.0
    profit: float = 0.0
    currency: str = ""
    server: str = ""
    leverage: int = 0
    trade_allowed: bool = False


class Quote(Frozen):
    symbol: str = ""
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    time: datetime = Field(default_factory=datetime.utcnow)

    @property
    def spread_price(self) -> float:
        return max(0.0, self.ask - self.bid)


class SymbolSpec(Frozen):
    name: str = ""
    digits: int = 5
    point: float = 0.00001
    bid: float = 0.0
    ask: float = 0.0
    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01
    trade_stops_level: int = 0
    tick_value: float = 1.0
    tick_size: float = 0.00001
    filling_mode: int = 2

    def pips_per_price(self) -> float:
        pip = self.point * 10
        return pip if pip > 0 else self.point

    def spread_pips(self) -> float:
        return (self.ask - self.bid) / self.pips_per_price() if self.ask > self.bid else 0.0


class Candle(Frozen):
    time: datetime = Field(default_factory=datetime.utcnow)
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    tick_volume: int = 0


class Position(Frozen):
    ticket: int = 0
    symbol: str = ""
    side: str = "BUY"
    volume: float = 0.0
    price_open: float = 0.0
    price_current: float = 0.0
    sl: float = 0.0
    tp: float = 0.0
    profit: float = 0.0
    magic: int = 0


class MarketOrderRequest(BaseModel):
    symbol: str = Field(min_length=1)
    side: str = "BUY"
    volume: float = Field(gt=0, le=1000)
    sl_price: float = 0.0
    tp_price: float = 0.0
    deviation_points: int = Field(default=20, ge=0, le=1000)
    magic: int = 0
    comment: str = "x-particle-g2"
    filling: str = "RETURN"


class OrderResult(Frozen):
    ok: bool = False
    retcode: int = 0
    deal: int = 0
    order: int = 0
    price: float = 0.0
    comment: str = ""
