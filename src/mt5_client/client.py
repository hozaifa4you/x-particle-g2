from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Protocol

from ..config import Settings
from .enums import FillingMode, OrderSide, Retcode, Timeframe, TradeAction
from .errors import MT5Error
from .models import Account, Candle, MarketOrderRequest, OrderResult, Position, Quote, SymbolSpec
from .rates import epoch_to_utc, rows_to_candles


class TerminalBackend(Protocol):
    def initialize(self, *args: Any, **kwargs: Any) -> bool: ...
    def shutdown(self) -> None: ...
    def last_error(self) -> object: ...
    def account_info(self) -> Any: ...
    def terminal_info(self) -> Any: ...
    def symbol_info(self, symbol: str) -> Any: ...
    def symbol_info_tick(self, symbol: str) -> Any: ...
    def symbol_select(self, symbol: str, enable: bool) -> bool: ...
    def copy_rates_from_pos(self, symbol: str, timeframe: int, start: int, count: int) -> Any: ...
    def order_check(self, request: dict[str, Any]) -> Any: ...
    def order_send(self, request: dict[str, Any]) -> Any: ...
    def positions_get(self, *args: Any, **kwargs: Any) -> Any: ...
    def order_calc_margin(self, *args: Any) -> Any: ...
    def login(self, *args: Any, **kwargs: Any) -> bool: ...


def _load_backend() -> TerminalBackend:
    import mt5_wrapper as raw  # type: ignore[import-untyped]

    return raw  # type: ignore[no-any-return]


class MT5Client:
    def __init__(self, settings: Settings, backend: TerminalBackend | None = None) -> None:
        self._settings = settings
        self._backend = backend or _load_backend()
        self._open = False

    def connect(self) -> None:
        args: dict[str, Any] = {}
        if self._settings.mt5_path:
            args["path"] = self._settings.mt5_path
        if self._settings.mt5_timeout_ms:
            args["timeout"] = self._settings.mt5_timeout_ms
        if self._settings.mt5_login:
            try:
                args["login"] = int(self._settings.mt5_login)
            except ValueError as err:
                raise MT5Error("MT5_LOGIN must be numeric") from err
        if self._settings.mt5_password:
            args["password"] = self._settings.mt5_password
        if self._settings.mt5_server:
            args["server"] = self._settings.mt5_server
        if not self._backend.initialize(**args):
            raise MT5Error("MT5 initialize failed", last_error=self._backend.last_error())
        terminal = self._backend.terminal_info()
        if terminal is not None and not bool(getattr(terminal, "connected", True)):
            self._backend.shutdown()
            raise MT5Error("MT5 terminal not connected", last_error=self._backend.last_error())
        self._open = True

    def close(self) -> None:
        try:
            self._backend.shutdown()
        finally:
            self._open = False

    def _need_open(self) -> TerminalBackend:
        if not self._open:
            raise MT5Error("MT5 client is not connected. Use mt5_session first.")
        return self._backend

    def account(self) -> Account:
        backend = self._need_open()
        info = backend.account_info()
        if info is None:
            raise MT5Error("account_info failed", last_error=backend.last_error())
        data = info._asdict() if hasattr(info, "_asdict") else dict(info)
        return Account(
            login=int(data.get("login", 0)),
            balance=float(data.get("balance", 0.0)),
            equity=float(data.get("equity", 0.0)),
            margin=float(data.get("margin", 0.0)),
            margin_free=float(data.get("margin_free", 0.0)),
            margin_level=float(data.get("margin_level", 0.0)),
            profit=float(data.get("profit", 0.0)),
            currency=str(data.get("currency", "")),
            server=str(data.get("server", "")),
            leverage=int(data.get("leverage", 0)),
            trade_allowed=bool(data.get("trade_allowed", False)),
        )

    def symbol(self, name: str) -> SymbolSpec:
        backend = self._need_open()
        info = backend.symbol_info(name)
        if info is None:
            raise MT5Error(f"Unknown symbol {name}", last_error=backend.last_error())
        data = info._asdict() if hasattr(info, "_asdict") else dict(info)
        if not bool(data.get("visible", True)):
            backend.symbol_select(name, True)
            info = backend.symbol_info(name)
            if info is None:
                raise MT5Error(f"Symbol {name} is not visible")
            data = info._asdict() if hasattr(info, "_asdict") else dict(info)
        tick = self.quote(name)
        return SymbolSpec(
            name=str(data.get("name", name)),
            digits=int(data.get("digits", 5)),
            point=float(data.get("point", 0.00001)),
            bid=tick.bid,
            ask=tick.ask,
            volume_min=float(data.get("volume_min", 0.01)),
            volume_max=float(data.get("volume_max", 100.0)),
            volume_step=float(data.get("volume_step", 0.01)),
            trade_stops_level=int(data.get("trade_stops_level", 0)),
            tick_value=float(data.get("trade_tick_value", data.get("tick_value", 1.0))),
            tick_size=float(data.get("trade_tick_size", data.get("tick_size", 0.00001))),
            filling_mode=int(data.get("filling_mode", 2)),
        )

    def quote(self, name: str) -> Quote:
        backend = self._need_open()
        tick = backend.symbol_info_tick(name)
        if tick is None:
            raise MT5Error(f"No tick for {name}", last_error=backend.last_error())
        data = tick._asdict() if hasattr(tick, "_asdict") else dict(tick)
        stamp = data.get("time_msc", data.get("time", 0))
        try:
            when = epoch_to_utc(int(int(stamp) / 1000) if int(stamp) > 10_000_000_000 else int(stamp))
        except (TypeError, ValueError):
            when = epoch_to_utc(0)
        return Quote(
            symbol=name,
            bid=float(data.get("bid", 0.0)),
            ask=float(data.get("ask", 0.0)),
            last=float(data.get("last", 0.0)),
            time=when,
        )

    def candles(self, symbol: str, timeframe: Timeframe, count: int = 300) -> list[Candle]:
        backend = self._need_open()
        rows = backend.copy_rates_from_pos(symbol, int(timeframe), 0, count)
        items: list[Candle] = rows_to_candles(rows)
        return items

    def positions(self, symbol: str | None = None) -> list[Position]:
        backend = self._need_open()
        raw = backend.positions_get(symbol=symbol) if symbol else backend.positions_get()
        if not raw:
            return []
        out: list[Position] = []
        for item in raw:
            data = item._asdict() if hasattr(item, "_asdict") else dict(item)
            side = "BUY" if int(data.get("type", 0)) == 0 else "SELL"
            out.append(
                Position(
                    ticket=int(data.get("ticket", 0)),
                    symbol=str(data.get("symbol", "")),
                    side=side,
                    volume=float(data.get("volume", 0.0)),
                    price_open=float(data.get("price_open", 0.0)),
                    price_current=float(data.get("price_current", 0.0)),
                    sl=float(data.get("sl", 0.0)),
                    tp=float(data.get("tp", 0.0)),
                    profit=float(data.get("profit", 0.0)),
                    magic=int(data.get("magic", 0)),
                )
            )
        return out

    def normalize_volume(self, spec: SymbolSpec, volume: float) -> float:
        step = spec.volume_step if spec.volume_step > 0 else 0.01
        clamped = min(max(volume, spec.volume_min), spec.volume_max)
        steps = round(clamped / step)
        return round(max(steps * step, spec.volume_min), 8)

    def filling_for(self, spec: SymbolSpec) -> FillingMode:
        mode = spec.filling_mode
        if mode & 2 == 2:
            return FillingMode.FOK
        if mode & 1 == 1:
            return FillingMode.IOC
        return FillingMode.RETURN

    def round_price(self, spec: SymbolSpec, price: float) -> float:
        return round(price, spec.digits)

    def send_market(self, order: MarketOrderRequest, spec: SymbolSpec) -> OrderResult:
        backend = self._need_open()
        side = OrderSide.BUY if order.side.upper() == "BUY" else OrderSide.SELL
        quote = self.quote(order.symbol)
        price = quote.ask if side == OrderSide.BUY else quote.bid
        volume = self.normalize_volume(spec, order.volume)
        sl = self.round_price(spec, order.sl_price)
        tp = self.round_price(spec, order.tp_price)
        try:
            filling = FillingMode[order.filling.upper()]
        except KeyError:
            filling = self.filling_for(spec)
        payload: dict[str, Any] = {
            "action": int(TradeAction.DEAL),
            "symbol": order.symbol,
            "volume": volume,
            "type": int(side),
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": order.deviation_points,
            "magic": order.magic or self._settings.magic_number,
            "comment": order.comment,
            "type_time": 0,
            "type_filling": int(filling),
        }
        check = backend.order_check(payload)
        if check is None or int(getattr(check, "retcode", -1)) != 0:
            comment = getattr(check, "comment", "order_check failed")
            raise MT5Error(f"order_check rejected: {comment}", last_error=backend.last_error())
        result = backend.order_send(payload)
        if result is None:
            raise MT5Error("order_send returned no result", last_error=backend.last_error())
        retcode = int(getattr(result, "retcode", -1))
        if retcode not in (int(Retcode.DONE), int(Retcode.PLACED), int(Retcode.DONE_PARTIAL)):
            raise MT5Error(
                f"order_send failed: {getattr(result, 'comment', '')}",
                retcode=retcode,
                last_error=backend.last_error(),
            )
        data = result._asdict() if hasattr(result, "_asdict") else {}
        return OrderResult(
            ok=True,
            retcode=retcode,
            deal=int(data.get("deal", 0)),
            order=int(data.get("order", 0)),
            price=float(data.get("price", price)),
            comment=str(data.get("comment", "")),
        )

    def close_position(self, ticket: int, deviation: int = 20) -> OrderResult:
        backend = self._need_open()
        found = backend.positions_get(ticket=ticket)
        if not found:
            raise MT5Error(f"No open position {ticket}")
        data = found[0]._asdict() if hasattr(found[0], "_asdict") else dict(found[0])
        symbol = str(data.get("symbol", ""))
        volume = float(data.get("volume", 0.0))
        is_buy = int(data.get("type", 0)) == 0
        quote = self.quote(symbol)
        spec = self.symbol(symbol)
        payload: dict[str, Any] = {
            "action": int(TradeAction.DEAL),
            "symbol": symbol,
            "volume": volume,
            "type": int(OrderSide.SELL if is_buy else OrderSide.BUY),
            "position": ticket,
            "price": quote.bid if is_buy else quote.ask,
            "deviation": deviation,
            "magic": self._settings.magic_number,
            "comment": "x-particle-g2 close",
            "type_time": 0,
            "type_filling": int(self.filling_for(spec)),
        }
        result = backend.order_send(payload)
        if result is None:
            raise MT5Error("close returned no result", last_error=backend.last_error())
        retcode = int(getattr(result, "retcode", -1))
        if retcode != int(Retcode.DONE):
            raise MT5Error(f"close failed: {getattr(result, 'comment', '')}", retcode=retcode)
        as_dict = result._asdict() if hasattr(result, "_asdict") else {}
        return OrderResult(
            ok=True,
            retcode=retcode,
            deal=int(as_dict.get("deal", 0)),
            order=int(as_dict.get("order", 0)),
            price=float(as_dict.get("price", 0.0)),
            comment=str(as_dict.get("comment", "")),
        )

    def margin_for(self, symbol: str, side: OrderSide, volume: float, price: float) -> float:
        backend = self._need_open()
        try:
            value = backend.order_calc_margin(int(side), symbol, volume, price)
        except Exception as exc:
            raise MT5Error(f"margin calc failed: {exc}") from exc
        if value is None:
            return 0.0
        return float(value)


@contextmanager
def mt5_session(settings: Settings, backend: TerminalBackend | None = None) -> Iterator[MT5Client]:
    client = MT5Client(settings, backend=backend)
    client.connect()
    try:
        yield client
    finally:
        client.close()


def _unused_datetime() -> datetime:

    return datetime.now(UTC)
