from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import aiohttp

REGIONAL = {
    "EUW1": "europe", "EUN1": "europe", "TR1": "europe", "RU": "europe",
    "NA1": "americas", "BR1": "americas", "LA1": "americas", "LA2": "americas",
    "KR": "asia", "JP1": "asia",
    "OC1": "sea",
}

RANKED_QUEUES = [420, 440]
NORMAL_QUEUES = [400, 430, 450]

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=30)

# ✅ Default slice size: 90 days (quarter-year).
# Change to 180 * 24 * 60 * 60 if you want half-year.
# Change to 90 * 24 * 60 * 60 if you want quater-year.
SLICE_SECONDS_DEFAULT = 180 * 24 * 60 * 60

# Safety: Riot endpoint uses count<=100.
PAGE_SIZE = 100


@dataclass
class SliceResult:
    count: int
    hit_full_pages: bool  # True if we kept getting full pages (suggests high activity in this slice)


def _label(label: str | None, puuid: str) -> str:
    # Helper for nicer debug logs
    if label:
        return f"{label} ({puuid[:8]}...)"
    return f"{puuid[:8]}..."


async def _fetch_ids_page(
    session: aiohttp.ClientSession,
    *,
    api_key: str,
    region: str,
    puuid: str,
    start_time_ts: int,
    end_time_ts: int | None,
    start: int,
    queue: int | None,
    debug: bool,
    label: str | None,
) -> list[str]:
    headers = {"X-Riot-Token": api_key}
    url = f"https://{region}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"

    params: dict[str, int] = {"startTime": start_time_ts, "start": start, "count": PAGE_SIZE}
    if end_time_ts is not None:
        params["endTime"] = end_time_ts
    if queue is not None:
        params["queue"] = queue

    tries = 0
    while True:
        async with session.get(url, headers=headers, params=params) as resp:
            if resp.status == 429:
                retry_after = resp.headers.get("Retry-After")
                wait_s = int(retry_after) if retry_after and retry_after.isdigit() else (2 ** min(tries, 5))
                tries += 1
                if debug:
                    print(f"[Match-V5] {_label(label, puuid)} 429 retry in {wait_s}s (try={tries})")
                await asyncio.sleep(wait_s)
                continue

            if resp.status == 403:
                body = await resp.text()
                raise RuntimeError(f"Forbidden (403) from Riot. body={body}")

            resp.raise_for_status()
            return await resp.json()


async def _count_ids_in_range(
    session: aiohttp.ClientSession,
    *,
    api_key: str,
    region: str,
    puuid: str,
    start_time_ts: int,
    end_time_ts: int | None,
    queue: int | None,
    debug: bool,
    label: str | None,
) -> SliceResult:
    total = 0
    start = 0
    hit_full_pages = False

    while True:
        ids = await _fetch_ids_page(
            session,
            api_key=api_key,
            region=region,
            puuid=puuid,
            start_time_ts=start_time_ts,
            end_time_ts=end_time_ts,
            start=start,
            queue=queue,
            debug=debug,
            label=label,
        )

        n = len(ids)
        total += n

        if debug:
            qtxt = f" queue={queue}" if queue is not None else ""
            etxt = f" endTime={end_time_ts}" if end_time_ts is not None else ""
            print(f"[Match-V5] {_label(label, puuid)}{qtxt} startTime={start_time_ts}{etxt} start={start} -> {n}")

        if n == PAGE_SIZE:
            hit_full_pages = True

        if n < PAGE_SIZE:
            break

        start += PAGE_SIZE

    return SliceResult(count=total, hit_full_pages=hit_full_pages)


def _queues_for_policy(queue_policy: str) -> list[int | None]:
    qp = (queue_policy or "all").strip().lower()
    if qp == "all":
        return [None]
    if qp == "ranked_only":
        return list(RANKED_QUEUES)
    if qp == "ranked_normal":
        return list(RANKED_QUEUES + NORMAL_QUEUES)
    raise ValueError(f"Unknown queue_policy: {queue_policy}")


async def count_lol_matches_since_filtered(
    *,
    api_key: str,
    puuid: str,
    platform: str,
    start_time_ts: int,
    queue_policy: str = "all",
    debug: bool = False,
    session: aiohttp.ClientSession | None = None,
    slice_seconds: int = SLICE_SECONDS_DEFAULT,
    label: str | None = None,  # ✅ NEW: for debug logs (e.g., riot_id or discord name)
) -> int:
    """
    Counts matches from start_time_ts up to now, filtered by queue_policy.
    Uses time-slicing (startTime + endTime) to avoid huge-range issues.
    """
    region = REGIONAL.get(platform.upper())
    if not region:
        raise ValueError(f"Unknown platform: {platform}")

    now_ts = int(datetime.now(timezone.utc).timestamp())
    if start_time_ts >= now_ts:
        return 0

    queues = _queues_for_policy(queue_policy)

    owns_session = session is None
    if owns_session:
        session = aiohttp.ClientSession(timeout=DEFAULT_TIMEOUT)

    try:
        assert session is not None

        total_all = 0

        t = start_time_ts
        slice_idx = 0
        while t < now_ts:
            end_t = min(t + slice_seconds, now_ts)

            for q in queues:
                res = await _count_ids_in_range(
                    session,
                    api_key=api_key,
                    region=region,
                    puuid=puuid,
                    start_time_ts=t,
                    end_time_ts=end_t,
                    queue=q,
                    debug=debug,
                    label=label,
                )
                total_all += res.count

            # ✅ Progress log: once every ~1 year worth of slices (works for 90d slices too)
            if debug and slice_idx % 4 == 0:
                print(f"[Match-V5] progress {_label(label, puuid)} t={t} -> {end_t} total={total_all}")

            t = end_t
            slice_idx += 1

        return total_all

    finally:
        if owns_session:
            await session.close()
