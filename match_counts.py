import aiohttp

REGIONAL = {
    "EUW1": "europe", "EUN1": "europe", "TR1": "europe", "RU": "europe",
    "NA1": "americas", "BR1": "americas", "LA1": "americas", "LA2": "americas",
    "KR": "asia", "JP1": "asia",
    "OC1": "sea",
}

async def count_lol_matches_since(api_key: str, puuid: str, platform: str, start_time_ts: int) -> int:
    """
    Counts ALL LoL match IDs since start_time_ts using Match-V5.
    TFT is not included because this is /lol/match/v5.
    """
    region = REGIONAL.get(platform.upper())
    if not region:
        raise ValueError(f"Unknown platform: {platform}")

    headers = {"X-Riot-Token": api_key}
    url = f"https://{region}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"

    total = 0
    start = 0
    batch = 100  # max allowed

    async with aiohttp.ClientSession() as session:
        while True:
            params = {"startTime": start_time_ts, "start": start, "count": batch}
            async with session.get(url, headers=headers, params=params) as resp:
                if resp.status == 429:
                    retry_after = resp.headers.get("Retry-After")
                    raise RuntimeError(f"Rate limited (429). Retry-After={retry_after}")
                resp.raise_for_status()
                match_ids = await resp.json()

            n = len(match_ids)
            total += n

            if n < batch:
                break
            start += batch

    return total

