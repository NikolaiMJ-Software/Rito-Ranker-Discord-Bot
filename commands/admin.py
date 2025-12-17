import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands
from discord import app_commands

import db
from utils_schedule import compute_next_refresh_ts
from leaderboard import refresh_leaderboard_for_guild

import traceback
from zoneinfo import ZoneInfo

from key import RIOT_API_KEY
from stats_update import update_stats_for_guild


WEEKDAYS = [
    ("monday", 0), ("tuesday", 1), ("wednesday", 2), ("thursday", 3),
    ("friday", 4), ("saturday", 5), ("sunday", 6),
]


@app_commands.default_permissions(administrator=True)
class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _is_admin(self, interaction: discord.Interaction) -> bool:
        # Extra runtime guard (nice during dev)
        return interaction.user.guild_permissions.administrator

    @app_commands.command(
        name="setleaderboard",
        description="Set the channel where the leaderboard is posted/updated.",
    )
    @app_commands.describe(channel="Channel for the leaderboard message")
    async def setleaderboard(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not self._is_admin(interaction):
            await interaction.response.send_message("❌ Admins only.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await db.ensure_guild_settings(interaction.guild_id)

        # Post a placeholder message and save its ID so we can edit it later
        msg = await channel.send("📊 Leaderboard initializing…")
        await db.set_leaderboard_message(interaction.guild_id, channel.id, msg.id)

        # Force an immediate refresh so it looks good right away
        await refresh_leaderboard_for_guild(self.bot, interaction.guild_id)

        await interaction.followup.send(
            f"✅ Leaderboard channel set to {channel.mention} and message created.",
            ephemeral=True,
        )

    @app_commands.command(name="setrefresh", description="Set weekly refresh schedule (Copenhagen time).")
    @app_commands.describe(weekday="monday..sunday", hour="0-23", minute="0-59")
    @app_commands.choices(weekday=[app_commands.Choice(name=name, value=val) for name, val in WEEKDAYS])
    async def setrefresh(self, interaction: discord.Interaction, weekday: app_commands.Choice[int], hour: int, minute: int):
        if not self._is_admin(interaction):
            await interaction.response.send_message("❌ Admins only.", ephemeral=True)
            return

        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            await interaction.response.send_message("❌ Invalid time. hour=0..23, minute=0..59", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await db.ensure_guild_settings(interaction.guild_id)

        tz_name = "Europe/Copenhagen"
        next_ts = compute_next_refresh_ts(
            now_utc=datetime.now(timezone.utc),
            weekday=weekday.value,
            hour=hour,
            minute=minute,
            tz_name=tz_name,
        )

        await db.set_refresh_schedule(
            guild_id=interaction.guild_id,
            refresh_weekday=weekday.value,
            refresh_hour=hour,
            refresh_minute=minute,
            refresh_tz=tz_name,
            next_refresh_ts=next_ts,
        )

        await interaction.followup.send(
            f"✅ Refresh set: {weekday.name.title()} {hour:02d}:{minute:02d} ({tz_name}).\n"
            f"Next refresh: <t:{next_ts}:F>",
            ephemeral=True,
        )

    @app_commands.command(name="setseason", description="Set current League season/split (resets leaderboard).")
    @app_commands.describe(
        season_key="Season key like S2025_SPLIT3",
        start_date="Season start date (YYYY-MM-DD, Copenhagen time)",
    )
    async def setseason(self, interaction: discord.Interaction, season_key: str, start_date: str):
        if not self._is_admin(interaction):
            await interaction.response.send_message("❌ Admins only.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            tz = ZoneInfo("Europe/Copenhagen")
            local_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=tz)
            start_ts = int(local_dt.astimezone(timezone.utc).timestamp())

            await db.ensure_guild_settings(interaction.guild_id)
            await db.set_season(
                guild_id=interaction.guild_id,
                season_key=season_key.strip(),
                season_start_ts=start_ts,
            )

            await interaction.followup.send(
                f"✅ Season set to `{season_key.strip()}`.\n"
                f"Start: `{start_date}` Copenhagen (stored as <t:{start_ts}:F>).\n"
                "Leaderboard will restart from this season start.",
                ephemeral=True,
            )

        except Exception:
            print("setseason crashed:\n", traceback.format_exc())
            await interaction.followup.send("❌ setseason failed. Check bot console.", ephemeral=True)

    @app_commands.command(name="refreshstatus", description="Show this server's refresh schedule and leaderboard setup.")
    async def refreshstatus(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await db.ensure_guild_settings(interaction.guild_id)
        gs = await db.get_guild_settings(interaction.guild_id)

        leaderboard_channel_id = gs.get("leaderboard_channel_id")
        leaderboard_message_id = gs.get("leaderboard_message_id")
        next_refresh_ts = gs.get("next_refresh_ts")
        last_refresh_ts = gs.get("last_refresh_ts")

        channel_txt = f"<#{leaderboard_channel_id}>" if leaderboard_channel_id else "Not set"
        msg_txt = f"`{leaderboard_message_id}`" if leaderboard_message_id else "Not set"
        next_txt = f"<t:{next_refresh_ts}:F>" if next_refresh_ts else "Not scheduled"
        last_txt = f"<t:{last_refresh_ts}:F>" if last_refresh_ts else "Never"

        season_key = gs.get("season_key") or "default"
        season_start_ts = gs.get("season_start_ts")
        season_start_txt = f"<t:{season_start_ts}:F>" if season_start_ts else "Not set"

        await interaction.followup.send(
            "📌 **Refresh status**\n"
            f"- Leaderboard channel: {channel_txt}\n"
            f"- Leaderboard message: {msg_txt}\n"
            f"- Schedule: weekday={gs.get('refresh_weekday')} "
            f"time={gs.get('refresh_hour', 0):02d}:{gs.get('refresh_minute', 0):02d} "
            f"tz={gs.get('refresh_tz')}\n"
            f"- Next refresh: {next_txt}\n"
            f"- Last refresh: {last_txt}\n"
            f"- Season key: `{season_key}`\n"
            f"- Season start: {season_start_txt}\n",
            ephemeral=True,
        )

    @app_commands.command(name="refreshnow", description="Force refresh the leaderboard immediately.")
    async def refreshnow(self, interaction: discord.Interaction):
        if not self._is_admin(interaction):
            await interaction.response.send_message("❌ Admins only.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await db.ensure_guild_settings(interaction.guild_id)

        gs = await db.get_guild_settings(interaction.guild_id)
        season_key = gs.get("season_key") or "default"
        season_start_ts = gs.get("season_start_ts")

        if not season_start_ts:
            await interaction.followup.send("❌ Run `/setseason` first (season start not set).", ephemeral=True)
            return

        # 1) Update stats from Riot
        updated = await update_stats_for_guild(
            guild=interaction.guild,
            riot_api_key=RIOT_API_KEY,
            season_key=season_key,
            season_start_ts=int(season_start_ts),
            max_concurrency=2,
        )

        # 2) Render leaderboard
        await refresh_leaderboard_for_guild(self.bot, interaction.guild_id)

        now_ts = int(time.time())
        await db.set_last_refresh_ts(interaction.guild_id, now_ts)

        await interaction.followup.send(
            f"✅ Leaderboard refreshed. Updated {updated} linked accounts.",
            ephemeral=True
        )



async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
