# bot.py
import asyncio
import discord
from discord.ext import commands

import db
from key import BOT_KEY

intents = discord.Intents.default()
intents.members = True  

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    await db.init_db()

    # Global sync (all servers)
    synced = await bot.tree.sync()
    print(f"Synced {len(synced)} global commands as {bot.user} ({bot.user.id})")


async def load_cogs():
    for ext in [
        "commands.general",
        "commands.accounts",
        "commands.scheduler",
        "commands.admin",
        "commands.leaderboard_commands",
    ]:
        try:
            await bot.load_extension(ext)
            print(f"Loaded {ext}")
        except Exception as e:
            print(f"FAILED to load {ext}: {e}")


async def main():
    async with bot:
        await load_cogs()
        await bot.start(BOT_KEY)


asyncio.run(main())
