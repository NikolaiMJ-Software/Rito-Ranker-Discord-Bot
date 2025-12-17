import hashlib
import discord
from discord.ext import commands
from discord import app_commands
import traceback

import db

PLATFORMS = [
    "EUW1", "EUN1", "NA1", "KR", "JP1",
    "BR1", "LA1", "LA2", "OC1", "TR1", "RU"
]

def fake_puuid(riot_id: str, platform: str) -> str:
    base = f"{riot_id.strip().lower()}|{platform.strip().upper()}".encode("utf-8")
    return hashlib.sha256(base).hexdigest()

class Accounts(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="link", description="Link a Riot account.")
    @app_commands.describe(
        riot_id="Riot ID like GameName#TAG",
        platform="Platform like EUW1 / EUN1 / NA1"
    )
    @app_commands.choices(platform=[app_commands.Choice(name=p, value=p) for p in PLATFORMS])
    async def link(self, interaction: discord.Interaction, riot_id: str, platform: app_commands.Choice[str]):
        riot_id = riot_id.strip()
        plat = platform.value

        if "#" not in riot_id or riot_id.startswith("#") or riot_id.endswith("#"):
            await interaction.response.send_message(
                "Please use the format `GameName#TAG`.",
                ephemeral=True
            )
            return

        puuid = fake_puuid(riot_id, plat)

        inserted = await db.add_riot_account(
            discord_user_id=interaction.user.id,
            puuid=puuid,
            riot_id=riot_id,
            platform=plat,
        )

        if inserted:
            await interaction.response.send_message(
                f"✅ Linked **{riot_id}** on **{plat}**.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "ℹ️ That Riot account is already linked.",
                ephemeral=True
            )

    @app_commands.command(name="accounts", description="Show your linked Riot accounts.")
    async def accounts(self, interaction: discord.Interaction):
        rows = await db.list_riot_accounts(interaction.user.id)

        if not rows:
            await interaction.response.send_message(
                "You have no linked accounts yet.",
                ephemeral=True
            )
            return

        lines = [
            f"- ID `{acc_id}`: **{riot_id or 'unknown'}** ({platform or 'unknown'})"
            for acc_id, _, riot_id, platform in rows
        ]

        await interaction.response.send_message(
            "Your linked accounts:\n" + "\n".join(lines),
            ephemeral=True
        )


    @app_commands.command(name="unlink", description="Unlink a Riot account by ID.")
    @app_commands.describe(account_id="The ID shown in /accounts")
    async def unlink(self, interaction: discord.Interaction, account_id: int):
        await interaction.response.defer(ephemeral=True)  # ACK immediately

        try:
            removed = await db.remove_riot_account(interaction.user.id, account_id)

            if removed:
                await interaction.followup.send(
                    f"🗑️ Unlinked account `{account_id}`.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "Account not found. Check `/accounts`.",
                    ephemeral=True
                )

        except Exception:
            print("Unlink crashed:\n", traceback.format_exc())
            await interaction.followup.send(
                "❌ Unlink failed due to a server error. Check bot console.",
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(Accounts(bot))
