from datetime import datetime, timedelta, time as dtime, timezone
from zoneinfo import ZoneInfo

def compute_next_refresh_ts(
    now_utc: datetime,
    weekday: int,
    hour: int,
    minute: int,
    tz_name: str = "Europe/Copenhagen",
) -> int:
    """
    Compute the next scheduled refresh time as a UTC unix timestamp.

    weekday: 0 = Monday ... 6 = Sunday
    hour/minute: local time in the given timezone
    """
    tz = ZoneInfo(tz_name)

    if weekday < 0 or weekday > 6:
        raise ValueError("weekday must be 0..6")
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("hour/minute invalid")

    # Convert now to local time
    now_local = now_utc.astimezone(tz)

    target_time = dtime(hour=hour, minute=minute)
    days_ahead = (weekday - now_local.weekday()) % 7
    candidate_date = now_local.date() + timedelta(days=days_ahead)

    candidate_local = datetime.combine(candidate_date, target_time, tzinfo=tz)

    # If the time already passed today, schedule next week
    if candidate_local <= now_local:
        candidate_local += timedelta(days=7)

    return int(candidate_local.astimezone(timezone.utc).timestamp())
