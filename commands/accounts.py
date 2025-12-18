import discord
from discord.ext import commands
from discord import app_commands
import traceback

import db
from key import RIOT_API_KEY
from riot_api import get_puuid_by_riot_id, RiotNotFound, RiotUnauthorized, RiotRateLimited

PLATFORMS = [
    "EUW1", "EUN1", "NA1", "KR", "JP1",
    "BR1", "LA1", "LA2", "OC1", "TR1", "RU"
]

REGION_CLUSTERS = ["europe", "americas", "asia", "sea"]

async def resolve_puuid_any_cluster(api_key: str, riot_id: str):
    for cluster in REGION_CLUSTERS:
        try:
            return await get_puuid_by_riot_id(api_key, riot_id, region_cluster=cluster)
        except RiotNotFound:
            continue
    raise RiotNotFound()


class Accounts(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="link", description="Link a Riot account (real Riot API).")
    @app_commands.describe(
        riot_id="Riot ID like GameName#TAG",
        platform="Platform like EUW1 / EUN1 / NA1"
    )
    @app_commands.choices(platform=[app_commands.Choice(name=p, value=p) for p in PLATFORMS])
    async def link(self, interaction: discord.Interaction, riot_id: str, platform: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=True)

        riot_id = riot_id.strip()
        plat = platform.value

        try:
            print("RIOT_API_KEY loaded:", RIOT_API_KEY[:10])
            puuid, game_name, tag_line = await resolve_puuid_any_cluster(RIOT_API_KEY, riot_id)
            canonical_riot_id = f"{game_name}#{tag_line}"

            inserted = await db.add_riot_account(
                discord_user_id=interaction.user.id,
                puuid=puuid,
                riot_id=canonical_riot_id,
                platform=plat,
            )

            if inserted:
                await interaction.followup.send(f"✅ Linked **{canonical_riot_id}** on **{plat}**.", ephemeral=True)
            else:
                await interaction.followup.send("ℹ️ That Riot account is already linked (PUUID exists).", ephemeral=True)

        except RiotNotFound:
            await interaction.followup.send("❌ Riot ID not found. Check spelling: `GameName#TAG`.", ephemeral=True)

        except RiotUnauthorized:
            await interaction.followup.send("❌ Riot API key invalid/expired or missing permissions.", ephemeral=True)

        except RiotRateLimited as e:
            msg = "⏳ Rate limited by Riot. Try again soon."
            if e.retry_after:
                msg += f" (Retry-After: {e.retry_after}s)"
            await interaction.followup.send(msg, ephemeral=True)

        except Exception:
            print("Link crashed:\n", traceback.format_exc())
            await interaction.followup.send("❌ Something went wrong. Check bot console.", ephemeral=True)

    @app_commands.command(name="accounts", description="Show your linked Riot accounts.")
    async def accounts(self, interaction: discord.Interaction):
        rows = await db.list_riot_accounts(interaction.user.id)

        if not rows:
            await interaction.response.send_message("You have no linked accounts yet.", ephemeral=True)
            return

        lines = [
            f"- ID `{acc_id}`: **{riot_id or 'unknown'}** ({platform or 'unknown'})"
            for acc_id, _, riot_id, platform in rows
        ]

        await interaction.response.send_message("Your linked accounts:\n" + "\n".join(lines), ephemeral=True)

    @app_commands.command(name="unlink", description="Unlink a Riot account by ID.")
    @app_commands.describe(account_id="The ID shown in /accounts")
    async def unlink(self, interaction: discord.Interaction, account_id: int):
        await interaction.response.defer(ephemeral=True)

        try:
            removed = await db.remove_riot_account(interaction.user.id, account_id)
            if removed:
                await interaction.followup.send(f"🗑️ Unlinked account `{account_id}`.", ephemeral=True)
            else:
                await interaction.followup.send("Account not found. Check `/accounts`.", ephemeral=True)

        except Exception:
            print("Unlink crashed:\n", traceback.format_exc())
            await interaction.followup.send("❌ Unlink failed due to a server error. Check bot console.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Accounts(bot))
