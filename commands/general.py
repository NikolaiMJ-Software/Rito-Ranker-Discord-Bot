import discord
from discord.ext import commands

class General(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @discord.app_commands.command(name="ping", description="Check if the bot is alive.")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message("Pong! 🏓", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(General(bot))
