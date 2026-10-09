from enum import IntEnum


class OrderSide(IntEnum):
    BUY = 0
    SELL = 1


class OrderType(IntEnum):
    BUY = 0
    SELL = 1
    BUY_LIMIT = 2
    SELL_LIMIT = 3
    BUY_STOP = 4
    SELL_STOP = 5
    BUY_STOP_LIMIT = 6
    SELL_STOP_LIMIT = 7
    CLOSE_BY = 8


class TradeAction(IntEnum):
    DEAL = 1
    PENDING = 5
    SLTP = 6
    MODIFY = 7
    REMOVE = 8
    CLOSE_BY = 10


class Timeframe(IntEnum):
    M1 = 1
    M5 = 5
    M15 = 15
    M30 = 30
    H1 = 1 | 0x4000
    H4 = 4 | 0x4000
    D1 = 24 | 0x4000
    W1 = 1 | 0x8000
    MN1 = 1 | 0xC000


NAME_TO_TIMEFRAME: dict[str, Timeframe] = {
    "M1": Timeframe.M1,
    "M5": Timeframe.M5,
    "M15": Timeframe.M15,
    "M30": Timeframe.M30,
    "H1": Timeframe.H1,
    "H4": Timeframe.H4,
    "D1": Timeframe.D1,
    "W1": Timeframe.W1,
    "MN1": Timeframe.MN1,
}


class FillingMode(IntEnum):
    FOK = 0
    IOC = 1
    RETURN = 2


class Retcode(IntEnum):
    DONE = 10009
    PLACED = 10008
    DONE_PARTIAL = 10010
    REQUOTE = 10004
    REJECT = 10006
    INVALID = 10013
    INVALID_VOLUME = 10014
    INVALID_PRICE = 10015
    INVALID_STOPS = 10016
    TRADE_DISABLED = 10017
    MARKET_CLOSED = 10018
    NO_MONEY = 10019
    PRICE_OFF = 10021
    TOO_MANY_REQUESTS = 10024
    CLIENT_DISABLES_AT = 10027
    CLOSE_ONLY = 10044
