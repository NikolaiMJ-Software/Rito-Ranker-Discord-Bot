import discord
from discord.ext import commands

from key import BOT_KEY
import db

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    await db.init_db()
    synced = await bot.tree.sync()
    print(f"Logged in as {bot.user}")
    print(f"Synced {len(synced)} slash commands")

async def load_cogs():
    await bot.load_extension("commands.general")
    await bot.load_extension("commands.accounts")

# Python 3.10+ recommended entrypoint
async def main():
    async with bot:
        await load_cogs()
        await bot.start(BOT_KEY)

import asyncio
asyncio.run(main())

