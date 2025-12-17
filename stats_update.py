import asyncio
from typing import List, Tuple

import db
from match_counts import count_lol_matches_since


async def update_stats_for_guild(guild, riot_api_key: str, season_key: str, season_start_ts: int, max_concurrency: int = 2) -> int:
    """
    Updates account_stats for all linked riot accounts belonging to members in this guild.
    Returns number of accounts updated.
    """
    member_ids = [str(m.id) for m in guild.members]
    accounts: List[Tuple[int, str, str]] = await db.list_accounts_for_users(member_ids)
    if not accounts:
        return 0

    sem = asyncio.Semaphore(max_concurrency)

    async def update_one(account_id: int, puuid: str, platform: str):
        async with sem:
            games = await count_lol_matches_since(riot_api_key, puuid, platform, int(season_start_ts))
            await db.upsert_account_stats(account_id, season_key, games)

    # Run with limited concurrency
    for account_id, puuid, platform in accounts:
        await update_one(account_id, puuid, platform)

    return len(accounts)
