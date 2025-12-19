# commands/general.py
import discord
from discord.ext import commands
from discord import app_commands


class General(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Check if the bot is alive.")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message("Pong! 🏓", ephemeral=True)

    @app_commands.command(name="help", description="Show bot commands and what they do.")
    async def help_cmd(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Rito Ranker — Commands",
            description="Leaderboard bot for counting LoL games in a chosen time window.",
            color=discord.Color.blue(),
        )

        embed.add_field(
            name="👤 Players",
            value=(
                "**/link** `GameName#TAG` + platform — Link your Riot account\n"
                "**/accounts** — Show your linked accounts\n"
                "**/unlink** `id` — Remove a linked account\n"
                "**/myrank** — See your current placement\n"
                "**/top** `n` — Show top N players (1–50)\n"
            ),
            inline=False,
        )

        embed.add_field(
            name="🛠️ Admins",
            value=(
                "**/setleaderboard** — Choose channel + create leaderboard message\n"
                "**/refreshnow** — Update stats + refresh leaderboard\n"
                "**/refreshstatus** — Show current configuration\n"
                "**/setrefresh** — Set automatic refresh schedule\n"
                "**/setwindow** — week / month / year window\n"
                "**/setfrom** — Count from custom date\n"
                "**/setqueues** — Choose which queues count\n"
            ),
            inline=False,
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(General(bot))
