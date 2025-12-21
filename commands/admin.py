# commands/admin.py
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands
from discord import app_commands

import db
from utilities.utils_schedule import compute_next_refresh_ts
from utilities.utils_window import compute_window_start_ts, make_window_key
from leaderboard import refresh_leaderboard_for_guild
from stats_update import update_stats_for_guild

# Riot API key (safe import so bot doesn't crash if missing)
try:
    from key import RIOT_API_KEY
except Exception:
    RIOT_API_KEY = None

# Riot API helper imports
from riot_api import get_puuid_by_riot_id, RiotNotFound, RiotUnauthorized, RiotRateLimited

# Platforms you support (must exist because /adminlink uses it)
PLATFORMS = [
    "EUW1", "EUN1", "NA1", "KR", "JP1",
    "BR1", "LA1", "LA2", "OC1", "TR1", "RU"
]

WEEKDAYS = [
    ("monday", 0), ("tuesday", 1), ("wednesday", 2), ("thursday", 3),
    ("friday", 4), ("saturday", 5), ("sunday", 6),
]

WINDOW_MODES = [
    ("week", "week"),
    ("month", "month"),
    ("year", "year"),
]

QUEUE_POLICIES = [
    ("all", "all"),
    ("ranked_only", "ranked_only"),
    ("ranked_normal", "ranked_normal"),
]

REGION_CLUSTERS = ["europe", "americas", "asia", "sea"]


async def resolve_puuid_any_cluster(api_key: str, riot_id: str):
    for cluster in REGION_CLUSTERS:
        try:
            return await get_puuid_by_riot_id(api_key, riot_id, region_cluster=cluster)
        except RiotNotFound:
            continue
    raise RiotNotFound()


@app_commands.default_permissions(administrator=True)
class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _is_admin(self, interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator

    # ---------- helpers ----------
    async def _compute_window(self, guild_id: int) -> tuple[str, int, str, str]:
        """
        Returns (window_key, window_start_ts, mode, tz_name)
        """
        gs = await db.get_guild_settings(guild_id)
        mode = (gs.get("window_mode") or "month").strip().lower()
        tz_name = gs.get("window_tz") or "Europe/Copenhagen"
        since_ts = gs.get("window_since_ts")

        window_start_ts = compute_window_start_ts(
            now_utc=datetime.now(timezone.utc),
            mode=mode,
            tz_name=tz_name,
            since_ts=since_ts,
        )
        window_key = make_window_key(mode, window_start_ts, tz_name)
        return window_key, window_start_ts, mode, tz_name

    # ---------------- Leaderboard placement ----------------
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

        msg = await channel.send("📊 Leaderboard initializing…")
        await db.set_leaderboard_message(interaction.guild_id, channel.id, msg.id)

        window_key, window_start_ts, mode, tz_name = await self._compute_window(interaction.guild_id)

        # Optional: fetch stats immediately for first render
        if RIOT_API_KEY:
            gs = await db.get_guild_settings(interaction.guild_id)
            queue_policy = (gs.get("queue_policy") or "all").strip().lower()

            await update_stats_for_guild(
                guild=interaction.guild,
                riot_api_key=RIOT_API_KEY,
                window_key=window_key,
                window_start_ts=window_start_ts,
                queue_policy=queue_policy,
                max_concurrency=2,
            )

        await refresh_leaderboard_for_guild(self.bot, interaction.guild_id, window_key)

        await interaction.followup.send(
            f"✅ Leaderboard channel set to {channel.mention} and message created.\n"
            f"Window: `{mode}` starting <t:{window_start_ts}:F> ({tz_name})",
            ephemeral=True,
        )

    # ---------------- Refresh schedule ----------------
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

    # ---------------- Window preference ----------------
    @app_commands.command(name="setwindow", description="Set leaderboard window mode (week/month/year).")
    @app_commands.choices(mode=[app_commands.Choice(name=n, value=v) for n, v in WINDOW_MODES])
    async def setwindow(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        if not self._is_admin(interaction):
            await interaction.response.send_message("❌ Admins only.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await db.ensure_guild_settings(interaction.guild_id)

        tz_name = "Europe/Copenhagen"
        await db.set_window_mode(interaction.guild_id, mode.value, tz_name)

        await interaction.followup.send(
            f"✅ Window mode set to **{mode.value}** ({tz_name}).\n"
            "Use `/refreshnow` to update immediately.",
            ephemeral=True,
        )

    @app_commands.command(name="setfrom", description="Set leaderboard to count from a custom date (YYYY-MM-DD).")
    @app_commands.describe(date="Start date in Copenhagen time, format YYYY-MM-DD")
    async def setfrom(self, interaction: discord.Interaction, date: str):
        if not self._is_admin(interaction):
            await interaction.response.send_message("❌ Admins only.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await db.ensure_guild_settings(interaction.guild_id)

        tz_name = "Europe/Copenhagen"
        tz = ZoneInfo(tz_name)

        try:
            local_dt = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=tz)
        except ValueError:
            await interaction.followup.send("❌ Invalid format. Use YYYY-MM-DD.", ephemeral=True)
            return

        since_ts = int(local_dt.astimezone(timezone.utc).timestamp())

        await db.set_window_mode(interaction.guild_id, "since_date", tz_name)
        await db.set_window_since_ts(interaction.guild_id, since_ts)

        await interaction.followup.send(
            f"✅ Window set to **since {date}** ({tz_name}).\n"
            f"Stored as <t:{since_ts}:F>.\n"
            "Use `/refreshnow` to update immediately.",
            ephemeral=True,
        )

    # ---------------- Queue policy ----------------
    @app_commands.command(name="setqueues", description="Set what queues count (all / ranked only / ranked+normal).")
    @app_commands.choices(policy=[app_commands.Choice(name=n, value=v) for n, v in QUEUE_POLICIES])
    async def setqueues(self, interaction: discord.Interaction, policy: app_commands.Choice[str]):
        if not self._is_admin(interaction):
            await interaction.response.send_message("❌ Admins only.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await db.ensure_guild_settings(interaction.guild_id)
        await db.set_queue_policy(interaction.guild_id, policy.value)

        await interaction.followup.send(f"✅ Queue policy set to `{policy.value}`.", ephemeral=True)

    # ---------------- Manual refresh + status ----------------
    @app_commands.command(name="refreshstatus", description="Show this server's refresh + window setup.")
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

        mode = (gs.get("window_mode") or "month").strip().lower()
        tz_name = gs.get("window_tz") or "Europe/Copenhagen"
        since_ts = gs.get("window_since_ts")
        since_txt = f"<t:{since_ts}:F>" if since_ts else "—"
        queue_policy = (gs.get("queue_policy") or "all").strip().lower()

        try:
            start_ts = compute_window_start_ts(datetime.now(timezone.utc), mode, tz_name, since_ts)
            start_txt = f"<t:{start_ts}:F>"
        except Exception:
            start_txt = "Error computing (check tz/mode)"

        await interaction.followup.send(
            "📌 **Status**\n"
            f"- Leaderboard channel: {channel_txt}\n"
            f"- Leaderboard message: {msg_txt}\n"
            f"- Next refresh: {next_txt}\n"
            f"- Last refresh: {last_txt}\n"
            f"- Window mode: `{mode}`\n"
            f"- Window tz: `{tz_name}`\n"
            f"- Window since: {since_txt}\n"
            f"- Window starts now at: {start_txt}\n"
            f"- Queue policy: `{queue_policy}`\n",
            ephemeral=True,
        )

    @app_commands.command(name="refreshnow", description="Force update stats and refresh leaderboard now.")
    async def refreshnow(self, interaction: discord.Interaction):
        if not self._is_admin(interaction):
            await interaction.response.send_message("❌ Admins only.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await db.ensure_guild_settings(interaction.guild_id)

        if not RIOT_API_KEY:
            await interaction.followup.send("❌ RIOT_API_KEY is missing in key.py", ephemeral=True)
            return

        gs = await db.get_guild_settings(interaction.guild_id)
        queue_policy = (gs.get("queue_policy") or "all").strip().lower()

        window_key, window_start_ts, mode, tz_name = await self._compute_window(interaction.guild_id)

        updated = await update_stats_for_guild(
            guild=interaction.guild,
            riot_api_key=RIOT_API_KEY,
            window_key=window_key,
            window_start_ts=window_start_ts,
            queue_policy=queue_policy,
            max_concurrency=2,
        )

        await refresh_leaderboard_for_guild(self.bot, interaction.guild_id, window_key)

        now_ts = int(time.time())
        await db.set_last_refresh_ts(interaction.guild_id, now_ts)

        await interaction.followup.send(
            f"✅ Refreshed. Updated {updated} linked accounts.\n"
            f"Window: `{mode}` start <t:{window_start_ts}:F> ({tz_name})\n"
            f"Queues: `{queue_policy}`",
            ephemeral=True,
        )

    # ---------------- Admin manage other users' links ----------------
    @app_commands.command(name="adminaccounts", description="(Admin) Show linked Riot accounts for a specific user.")
    @app_commands.describe(user="The Discord user to check")
    async def adminaccounts(self, interaction: discord.Interaction, user: discord.Member):
        if not self._is_admin(interaction):
            await interaction.response.send_message("❌ Admins only.", ephemeral=True)
            return

        rows = await db.list_riot_accounts(user.id)
        if not rows:
            await interaction.response.send_message(f"ℹ️ {user.mention} has no linked accounts.", ephemeral=True)
            return

        lines = [
            f"- ID `{acc_id}`: **{riot_id or 'unknown'}** ({platform or 'unknown'})"
            for acc_id, _, riot_id, platform in rows
        ]
        await interaction.response.send_message(
            f"📌 Linked accounts for {user.mention}:\n" + "\n".join(lines),
            ephemeral=True,
        )

    @app_commands.command(name="adminlink", description="(Admin) Link a Riot account to a specific Discord user.")
    @app_commands.describe(user="Discord user", riot_id="Riot ID like GameName#TAG", platform="EUW1/EUN1/NA1 etc.")
    @app_commands.choices(platform=[app_commands.Choice(name=p, value=p) for p in PLATFORMS])
    async def adminlink(self, interaction: discord.Interaction, user: discord.Member, riot_id: str, platform: app_commands.Choice[str]):
        if not self._is_admin(interaction):
            await interaction.response.send_message("❌ Admins only.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        if not RIOT_API_KEY:
            await interaction.followup.send("❌ RIOT_API_KEY missing.", ephemeral=True)
            return

        riot_id = riot_id.strip()
        plat = platform.value

        try:
            puuid, game_name, tag_line = await resolve_puuid_any_cluster(RIOT_API_KEY, riot_id)
            canonical_riot_id = f"{game_name}#{tag_line}"

            inserted = await db.add_riot_account(
                discord_user_id=user.id,
                puuid=puuid,
                riot_id=canonical_riot_id,
                platform=plat,
            )

            if inserted:
                await interaction.followup.send(
                    f"✅ Linked **{canonical_riot_id}** on **{plat}** to {user.mention}.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    "ℹ️ That Riot account (PUUID) is already linked somewhere.",
                    ephemeral=True,
                )

        except RiotNotFound:
            await interaction.followup.send("❌ Riot ID not found. Check spelling: `GameName#TAG`.", ephemeral=True)
        except RiotUnauthorized:
            await interaction.followup.send("❌ Riot API key invalid/expired or missing permissions.", ephemeral=True)
        except RiotRateLimited as e:
            msg = "⏳ Rate limited by Riot. Try again soon."
            retry_after = getattr(e, "retry_after", None)
            if retry_after:
                msg += f" (Retry-After: {retry_after}s)"
            await interaction.followup.send(msg, ephemeral=True)
        except Exception as ex:
            await interaction.followup.send(f"❌ adminlink failed: `{ex}`", ephemeral=True)

    @app_commands.command(name="adminunlink", description="(Admin) Unlink a Riot account from a specific user by account ID.")
    @app_commands.describe(user="Discord user", account_id="The ID shown in /adminaccounts")
    async def adminunlink(self, interaction: discord.Interaction, user: discord.Member, account_id: int):
        if not self._is_admin(interaction):
            await interaction.response.send_message("❌ Admins only.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        removed = await db.remove_riot_account(user.id, account_id)
        if removed:
            await interaction.followup.send(f"🗑️ Unlinked account `{account_id}` from {user.mention}.", ephemeral=True)
        else:
            await interaction.followup.send(f"ℹ️ No account `{account_id}` found for {user.mention}.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
