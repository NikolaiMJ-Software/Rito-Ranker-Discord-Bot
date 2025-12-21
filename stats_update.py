# stats_update.py
import asyncio
from typing import List, Tuple

import aiohttp
import db
from match_counts import count_lol_matches_since_filtered, DEFAULT_TIMEOUT


async def update_stats_for_guild(
    guild,
    riot_api_key: str,
    window_key: str,
    window_start_ts: int,
    queue_policy: str = "all",
    max_concurrency: int = 2,
) -> int:
    member_ids = [str(m.id) for m in guild.members]
    accounts: List[Tuple[int, str, str]] = await db.list_accounts_for_users(member_ids)
    if not accounts:
        return 0

    sem = asyncio.Semaphore(max_concurrency)

    async with aiohttp.ClientSession(timeout=DEFAULT_TIMEOUT) as session:

        async def update_one(account_id: int, puuid: str, platform: str):
            async with sem:
                label = await db.get_account_label(account_id)
                print(f"[Stats] Counting for {label} | policy={queue_policy} | window_key={window_key}")

                games = await count_lol_matches_since_filtered(
                    api_key=riot_api_key,
                    puuid=puuid,
                    platform=platform,
                    start_time_ts=window_start_ts,
                    queue_policy=queue_policy,
                    session=session,
                    debug=True,  # keep while testing
                )
                print(f"[Stats] DONE {label} -> games={games}")

                await db.upsert_account_stats(account_id, window_key, games)

        await asyncio.gather(*(update_one(a, p, plat) for a, p, plat in accounts))

    return len(accounts)
