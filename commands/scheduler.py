import time
from datetime import datetime, timezone

from discord.ext import commands, tasks

import db
from leaderboard import refresh_leaderboard_for_guild
from stats_update import update_stats_for_guild
from utils_schedule import compute_next_refresh_ts
from utils_window import compute_window_start_ts, make_window_key

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

        guild_rows = await db.list_guild_refresh_due(now_ts)
        if not guild_rows:
            return

        for g in guild_rows:
            guild_id = int(g["guild_id"])
            guild = self.bot.get_guild(guild_id)

            if guild is None:
                continue  # bot left guild

            try:
                if not RIOT_API_KEY:
                    print(f"[Scheduler] Guild {guild_id}: RIOT_API_KEY missing — skipping stats update")
                    # Still schedule next refresh so it doesn't spam "due"
                    next_ts = compute_next_refresh_ts(
                        now_utc=datetime.now(timezone.utc),
                        weekday=g["refresh_weekday"],
                        hour=g["refresh_hour"],
                        minute=g["refresh_minute"],
                        tz_name=g["refresh_tz"],
                    )
                    await db.set_next_refresh_ts(guild_id, next_ts)
                    continue

                # ----- Window preference -----
                mode = (g.get("window_mode") or "month").strip().lower()
                tz_name = g.get("window_tz") or "Europe/Copenhagen"
                since_ts = g.get("window_since_ts")

                window_start_ts = compute_window_start_ts(
                    now_utc=datetime.now(timezone.utc),
                    mode=mode,
                    tz_name=tz_name,
                    since_ts=since_ts,
                )
                window_key = make_window_key(mode, window_start_ts, tz_name)
                queue_policy = (g.get("queue_policy") or "all").strip().lower()

                # 1) Update Riot stats -> writes account_stats(account_id, window_key)
                updated_accounts = await update_stats_for_guild(
                    guild=guild,
                    riot_api_key=RIOT_API_KEY,
                    window_key=window_key,
                    window_start_ts=window_start_ts,
                    queue_policy=queue_policy,
                    max_concurrency=2,
                )


                # 2) Refresh leaderboard message -> reads account_stats for window_key
                await refresh_leaderboard_for_guild(self.bot, guild_id, window_key)


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
                    f"[Scheduler] Guild {guild_id}: updated {updated_accounts} accounts | "
                    f"queues={queue_policy} | window={mode} start=<t:{window_start_ts}:F> | next=<t:{next_ts}:F>"
                )


            except Exception as e:
                print(f"[Scheduler] Guild {guild_id}: refresh failed: {e}")

                # Even on failure, schedule next refresh so it doesn't retry every minute forever
                try:
                    next_ts = compute_next_refresh_ts(
                        now_utc=datetime.now(timezone.utc),
                        weekday=g["refresh_weekday"],
                        hour=g["refresh_hour"],
                        minute=g["refresh_minute"],
                        tz_name=g["refresh_tz"],
                    )
                    await db.set_next_refresh_ts(guild_id, next_ts)
                except Exception:
                    pass

    @refresh_loop.before_loop
    async def before_refresh_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Scheduler(bot))



