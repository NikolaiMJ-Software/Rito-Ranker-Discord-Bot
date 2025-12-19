# commands/leaderboard_commands.py
from __future__ import annotations

from datetime import datetime, timezone

import discord
from discord.ext import commands
from discord import app_commands

import db
from utilities.utils_window import compute_window_start_ts, make_window_key

MAX_TOP_LIMIT = 50
MIN_TOP_LIMIT = 1


def _tier_emoji_for_rank(rank: int) -> str:
    """
    'Rank tier' here means leaderboard tier by placement (not LoL rank).
    Tune these however you want.
    """
    if rank == 1:
        return "👑"  # Challenger-ish
    if rank <= 3:
        return "🔥"  # top 3
    if rank <= 10:
        return "💎"  # top 10
    return "💩"


def _medal(rank: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"**{rank}.**")


async def _current_window_key(guild_id: int) -> tuple[str, int, str, str, str]:
    """
    Returns: (window_key, window_start_ts, window_mode, tz_name, queue_policy)
    """
    gs = await db.get_guild_settings(guild_id)

    mode = (gs.get("window_mode") or "month").strip().lower()
    tz_name = gs.get("window_tz") or "Europe/Copenhagen"
    since_ts = gs.get("window_since_ts")

    queue_policy = (gs.get("queue_policy") or "all").strip().lower()

    start_ts = compute_window_start_ts(
        now_utc=datetime.now(timezone.utc),
        mode=mode,
        tz_name=tz_name,
        since_ts=since_ts,
    )
    window_key = make_window_key(mode, start_ts, tz_name)
    return window_key, start_ts, mode, tz_name, queue_policy


async def _get_rows_for_guild(guild: discord.Guild, window_key: str) -> list[tuple[str, int]]:
    member_ids = {str(m.id) for m in guild.members}
    rows = await db.get_guild_leaderboard_rows(list(member_ids), window_key=window_key)
    rows = sorted(rows, key=lambda r: r[1], reverse=True)
    return rows


class LeaderboardCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="top", description="Show top N players (default 10).")
    @app_commands.describe(n="How many to show (1-50)")
    async def top(self, interaction: discord.Interaction, n: int = 10):
        await interaction.response.defer(ephemeral=True)

        if n < MIN_TOP_LIMIT or n > MAX_TOP_LIMIT:
            await interaction.followup.send(f"❌ n must be between {MIN_TOP_LIMIT} and {MAX_TOP_LIMIT}.", ephemeral=True)
            return

        if not interaction.guild:
            await interaction.followup.send("❌ This command only works in a server.", ephemeral=True)
            return

        window_key, start_ts, mode, tz_name, queue_policy = await _current_window_key(interaction.guild_id)
        rows = await _get_rows_for_guild(interaction.guild, window_key)

        if not rows:
            await interaction.followup.send("No data yet. Users must `/link` and an admin must `/refreshnow`.", ephemeral=True)
            return

        top_rows = rows[:n]

        lines = []
        for idx, (duid, games) in enumerate(top_rows, start=1):
            tier = _tier_emoji_for_rank(idx)
            lines.append(f"{_medal(idx)} {tier} <@{duid}> — **{games}**")

        embed = discord.Embed(
            title=f"🏆 Top {n}",
            description=(
                f"Window: `{mode}` | Start: <t:{start_ts}:d> | TZ: `{tz_name}`\n"
                f"Queues: `{queue_policy}`"
            ),
        )
        embed.add_field(name="Leaderboard", value="\n".join(lines), inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="myrank", description="Show your current placement on the leaderboard.")
    async def myrank(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if not interaction.guild:
            await interaction.followup.send("❌ This command only works in a server.", ephemeral=True)
            return

        window_key, start_ts, mode, tz_name, queue_policy = await _current_window_key(interaction.guild_id)
        rows = await _get_rows_for_guild(interaction.guild, window_key)

        if not rows:
            await interaction.followup.send("No data yet. Users must `/link` and an admin must `/refreshnow`.", ephemeral=True)
            return

        my_id = str(interaction.user.id)

        # Find your placement
        rank = None
        games = None
        for i, (duid, g) in enumerate(rows, start=1):
            if duid == my_id:
                rank = i
                games = g
                break

        if rank is None:
            await interaction.followup.send(
                "You're not on the board yet.\n"
                "Make sure you have linked an account with `/link`, then ask an admin to `/refreshnow`.",
                ephemeral=True,
            )
            return

        tier = _tier_emoji_for_rank(rank)
        embed = discord.Embed(
            title="📍 Your Rank",
            description=(
                f"You are **#{rank}** {tier}\n"
                f"Games: **{games}**\n\n"
                f"Window: `{mode}` | Start: <t:{start_ts}:d> | TZ: `{tz_name}`\n"
                f"Queues: `{queue_policy}`"
            ),
        )

        # Optional: show who is #1
        top_user_id = int(rows[0][0])
        top_games = rows[0][1]
        embed.add_field(name="👑 #1 Right Now", value=f"<@{top_user_id}> — **{top_games}**", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(LeaderboardCommands(bot))
