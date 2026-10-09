import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel


class JournalEntry(BaseModel):
    time: datetime = datetime.now(UTC)
    symbol: str = ""
    action: str = "NO_TRADE"
    side: str = ""
    volume: float = 0.0
    reason: str = ""
    sl_pips: float = 0.0
    tp_pips: float = 0.0
    dry_run: bool = True


class Journal:
    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: JournalEntry) -> None:
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(entry.model_dump_json() + "\n")

    def today_entries(self, now: datetime) -> list[JournalEntry]:
        if not self._path.exists():
            return []
        out: list[JournalEntry] = []
        day = now.date()
        for line in self._path.read_text(encoding="utf-8").splitlines():
            try:
                item = JournalEntry.model_validate(json.loads(line))
            except ValueError:
                continue
            stamp = item.time
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=UTC)
            if stamp.date() == day and item.action == "EXECUTE":
                out.append(item)
        return out

    def last_trade_time(self) -> datetime | None:
        if not self._path.exists():
            return None
        last: datetime | None = None
        for line in self._path.read_text(encoding="utf-8").splitlines():
            try:
                item = JournalEntry.model_validate(json.loads(line))
            except ValueError:
                continue
            if item.action != "EXECUTE":
                continue
            stamp = item.time
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=UTC)
            last = stamp if last is None or stamp > last else last
        return last
