# commands/scheduler.py
import time
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

import db
from leaderboard import refresh_leaderboard_for_guild
from stats_update import update_stats_for_guild
from utilities.utils_schedule import compute_next_refresh_ts
from utilities.utils_window import compute_window_start_ts, make_window_key

# Riot API key (safe import so bot doesn't crash if missing)
try:
    from key import RIOT_API_KEY
except Exception:
    RIOT_API_KEY = None


def _shame_line(name: str, gained: int) -> str:
    if gained >= 40:
        return f"🫵 **{name}** gained **+{gained}**. Get a life ma man!"
    if gained >= 20:
        return f"😤 **{name}** gained **+{gained}**. Touch grass."
    if gained >= 10:
        return f"😏 **{name}** gained **+{gained}**. Solid grind."
    if gained > 0:
        return f"🙂 **{name}** gained **+{gained}**."
    return f"🧊 **{name}** gained **0**. Chill week."


async def _post_weekly_announcement(
    bot: discord.Client,
    guild: discord.Guild,
    guild_id: int,
    window_key: str,
) -> None:
    """
    Posts a fun 'weekly shame' announcement in the leaderboard channel.
    Uses snapshot delta: (current games_played - previous snapshot games_played).
    """
    gs = await db.get_guild_settings(guild_id)
    channel_id = gs.get("leaderboard_channel_id")
    if not channel_id:
        return

    channel = guild.get_channel(int(channel_id))
    if channel is None or not isinstance(channel, (discord.TextChannel, discord.Thread)):
        return

    # Current totals (top 3)
    member_ids = [str(m.id) for m in guild.members]
    rows = await db.get_guild_leaderboard_rows(member_ids, window_key)  # [(duid, total)]
    if not rows:
        return

    # stable ordering: total desc, user id asc
    rows = sorted(rows, key=lambda r: (-r[1], int(r[0])))[:3]

    prev = await db.get_snapshot_map(guild_id, window_key)  # {duid: (rank, games)}

    lines: list[str] = []
    for duid, total in rows:
        prev_rank, prev_games = prev.get(duid, (None, None))
        gained = total - prev_games if prev_games is not None else total

        member = guild.get_member(int(duid))
        name = member.display_name if member else f"<@{duid}>"
        lines.append(_shame_line(name, gained))

    # Window label
    window_mode = (gs.get("window_mode") or "month").strip().lower()
    queue_policy = (gs.get("queue_policy") or "all").replace("_", " ").title()

    msg = (
        f"📢 **Weekly update** — window `{window_mode}`, queues **{queue_policy}**\n"
        + "\n".join(lines)
    )
    await channel.send(msg)


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
                # Always reschedule next refresh even if we bail early
                async def _schedule_next():
                    next_ts = compute_next_refresh_ts(
                        now_utc=datetime.now(timezone.utc),
                        weekday=g["refresh_weekday"],
                        hour=g["refresh_hour"],
                        minute=g["refresh_minute"],
                        tz_name=g["refresh_tz"],
                    )
                    await db.set_next_refresh_ts(guild_id, next_ts)
                    return next_ts

                if not RIOT_API_KEY:
                    print(f"[Scheduler] Guild {guild_id}: RIOT_API_KEY missing — skipping stats update")
                    next_ts = await _schedule_next()
                    print(f"[Scheduler] Guild {guild_id}: next_refresh_ts={next_ts}")
                    continue

                mode = (g.get("window_mode") or "month").strip().lower()
                tz_name = g.get("window_tz") or "Europe/Copenhagen"
                since_ts = g.get("window_since_ts")
                queue_policy = (g.get("queue_policy") or "all").strip().lower()

                window_start_ts = compute_window_start_ts(
                    now_utc=datetime.now(timezone.utc),
                    mode=mode,
                    tz_name=tz_name,
                    since_ts=since_ts,
                )
                window_key = make_window_key(mode, window_start_ts, tz_name)

                # 1) Update Riot stats
                updated_accounts = await update_stats_for_guild(
                    guild=guild,
                    riot_api_key=RIOT_API_KEY,
                    window_key=window_key,
                    window_start_ts=window_start_ts,
                    queue_policy=queue_policy,
                    max_concurrency=2,
                )

                # 2) Optional announcement FIRST (uses previous snapshot)
                # If you only want it on weekly windows, uncomment this:
                # if mode == "week":
                await _post_weekly_announcement(self.bot, guild, guild_id, window_key)

                # 3) Refresh leaderboard embed (this writes snapshot rows)
                await refresh_leaderboard_for_guild(self.bot, guild_id, window_key)

                # 4) Mark last refresh
                await db.set_last_refresh_ts(guild_id, now_ts)

                # 5) Schedule next refresh
                next_ts = await _schedule_next()

                print(
                    f"[Scheduler] Guild {guild_id}: updated={updated_accounts} "
                    f"queue_policy={queue_policy} mode={mode} "
                    f"window_start_ts={window_start_ts} next_refresh_ts={next_ts}"
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
