# match_counts.py
from __future__ import annotations
import aiohttp

REGIONAL = {
    "EUW1": "europe", "EUN1": "europe", "TR1": "europe", "RU": "europe",
    "NA1": "americas", "BR1": "americas", "LA1": "americas", "LA2": "americas",
    "KR": "asia", "JP1": "asia",
    "OC1": "sea",
}

# Common LoL queue IDs (can be adjusted)
RANKED_QUEUES = [420, 440]          # Solo/Duo, Flex
NORMAL_QUEUES = [400, 430, 450]     # Normal Draft, Normal Blind, ARAM

async def _count_ids(
    session: aiohttp.ClientSession,
    *,
    api_key: str,
    region: str,
    puuid: str,
    start_time_ts: int,
    queue: int | None = None,
    debug: bool = False,
) -> int:
    headers = {"X-Riot-Token": api_key}
    url = f"https://{region}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"

    total = 0
    start = 0
    batch = 100

    while True:
        params = {"startTime": start_time_ts, "start": start, "count": batch}
        if queue is not None:
            params["queue"] = queue

        async with session.get(url, headers=headers, params=params) as resp:
            if resp.status == 429:
                retry_after = resp.headers.get("Retry-After")
                raise RuntimeError(f"Rate limited (429). Retry-After={retry_after}")
            resp.raise_for_status()
            match_ids = await resp.json()

        n = len(match_ids)
        total += n

        if debug:
            qtxt = f" queue={queue}" if queue is not None else ""
            print(f"[Match-V5]{qtxt} start={start} -> {n}")

        if n < batch:
            break
        start += batch

    return total


async def count_lol_matches_since_filtered(
    *,
    api_key: str,
    puuid: str,
    platform: str,
    start_time_ts: int,
    queue_policy: str = "all",
    debug: bool = False,
) -> int:
    region = REGIONAL.get(platform.upper())
    if not region:
        raise ValueError(f"Unknown platform: {platform}")

    queue_policy = (queue_policy or "all").strip().lower()

    if debug:
        print(
            f"[Match-V5] policy={queue_policy} puuid={puuid[:8]}... "
            f"platform={platform} region={region} startTime={start_time_ts}"
        )

    async with aiohttp.ClientSession() as session:
        if queue_policy == "all":
            return await _count_ids(
                session,
                api_key=api_key,
                region=region,
                puuid=puuid,
                start_time_ts=start_time_ts,
                queue=None,
                debug=debug,
            )

        if queue_policy == "ranked_only":
            totals = [
                await _count_ids(session, api_key=api_key, region=region, puuid=puuid,
                                 start_time_ts=start_time_ts, queue=q, debug=debug)
                for q in RANKED_QUEUES
            ]
            return sum(totals)

        if queue_policy == "ranked_normal":
            queues = RANKED_QUEUES + NORMAL_QUEUES
            totals = [
                await _count_ids(session, api_key=api_key, region=region, puuid=puuid,
                                 start_time_ts=start_time_ts, queue=q, debug=debug)
                for q in queues
            ]
            return sum(totals)

        raise ValueError(f"Unknown queue_policy: {queue_policy}")
