from datetime import datetime

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def weekday_name(when: datetime) -> str:
    return WEEKDAYS[when.weekday()]


def is_off_day(when: datetime, off_days: list[str]) -> bool:
    return weekday_name(when) in off_days


def is_friday_lockout(when: datetime, cutoff_hour: int) -> bool:
    return weekday_name(when) == "Friday" and when.hour >= cutoff_hour


def cooldown_remaining(last_time: datetime | None, now: datetime, minutes: int) -> int:
    if last_time is None:
        return 0
    elapsed = (now - last_time).total_seconds() / 60
    return max(0, int(minutes - elapsed))
