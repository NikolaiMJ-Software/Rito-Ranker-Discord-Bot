from __future__ import annotations
from datetime import datetime, timedelta, time as dtime, timezone
from zoneinfo import ZoneInfo

def compute_window_start_ts(now_utc: datetime, mode: str, tz_name: str, since_ts: int | None) -> int:
    tz = ZoneInfo(tz_name)
    now_local = now_utc.astimezone(tz)

    if mode == "since_date":
        if not since_ts:
            raise ValueError("since_date mode requires window_since_ts")
        return int(since_ts)

    if mode == "week":
        # Monday 00:00 local
        monday = now_local.date() - timedelta(days=now_local.weekday())
        start_local = datetime.combine(monday, dtime(0, 0), tzinfo=tz)

    elif mode == "month":
        first = now_local.date().replace(day=1)
        start_local = datetime.combine(first, dtime(0, 0), tzinfo=tz)

    elif mode == "year":
        first = now_local.date().replace(month=1, day=1)
        start_local = datetime.combine(first, dtime(0, 0), tzinfo=tz)

    else:
        raise ValueError(f"Unknown window_mode: {mode}")

    return int(start_local.astimezone(timezone.utc).timestamp())


def make_window_key(mode: str, start_ts: int, tz_name: str) -> str:
    # Unique enough for caching + multi-guild support
    return f"{mode}:{tz_name}:{start_ts}"
