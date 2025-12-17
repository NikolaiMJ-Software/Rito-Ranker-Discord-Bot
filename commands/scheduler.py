import time
from datetime import datetime, timezone

from discord.ext import commands, tasks

import db
from leaderboard import refresh_leaderboard_for_guild
from stats_update import update_stats_for_guild
from utils_schedule import compute_next_refresh_ts

# Riot API key (safe import so bot doesn't crash if missing)
try:
    from key import RIOT_API_KEY
except Exception:
    RIOT_API_KEY = None


class Scheduler(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.refresh_loop.start()

    def cog_unload(self):
        self.refresh_loop.cancel()

    @tasks.loop(seconds=60)
    async def refresh_loop(self):
        now_ts = int(time.time())

        # Which guilds are due for refresh?
        guild_rows = await db.list_guild_refresh_due(now_ts)
        if not guild_rows:
            return

        for g in guild_rows:
            guild_id = int(g["guild_id"])
            guild = self.bot.get_guild(guild_id)

            if guild is None:
                # Bot might have left the guild
                continue

            try:
                season_key = g.get("season_key") or "default"
                season_start_ts = g.get("season_start_ts")

                if not season_start_ts:
                    print(f"[Scheduler] Guild {guild_id}: no season set (run /setseason) — skipping")
                    continue

                if not RIOT_API_KEY:
                    print(f"[Scheduler] Guild {guild_id}: RIOT_API_KEY missing — skipping stats update")
                    continue

                # 1) Update Riot stats -> writes account_stats
                updated_accounts = await update_stats_for_guild(
                    guild=guild,
                    riot_api_key=RIOT_API_KEY,
                    season_key=season_key,
                    season_start_ts=int(season_start_ts),
                    max_concurrency=2,
                )

                # 2) Refresh leaderboard message -> reads account_stats
                await refresh_leaderboard_for_guild(self.bot, guild_id)

                # 3) Mark last refresh
                await db.set_last_refresh_ts(guild_id, now_ts)

                # 4) Compute + store next refresh timestamp
                next_ts = compute_next_refresh_ts(
                    now_utc=datetime.now(timezone.utc),
                    weekday=g["refresh_weekday"],
                    hour=g["refresh_hour"],
                    minute=g["refresh_minute"],
                    tz_name=g["refresh_tz"],
                )
                await db.set_next_refresh_ts(guild_id, next_ts)

                print(
                    f"[Scheduler] Guild {guild_id}: updated {updated_accounts} accounts, "
                    f"next refresh <t:{next_ts}:F>"
                )

            except Exception as e:
                print(f"[Scheduler] Guild {guild_id}: refresh failed: {e}")

    @refresh_loop.before_loop
    async def before_refresh_loop(self):
        # Ensure bot is logged in and cache is ready (guilds/channels/members)
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Scheduler(bot))


