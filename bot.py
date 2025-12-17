import discord
from discord.ext import commands

from key import BOT_KEY
import db

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

GUILD_ID = 252488961493041154  # your server id

@bot.event
async def on_ready():
    await db.init_db()
    guild = discord.Object(id=GUILD_ID)
    bot.tree.copy_global_to(guild=guild)
    synced = await bot.tree.sync(guild=guild)
    print(f"Synced {len(synced)} commands to guild {GUILD_ID}")


async def load_cogs():
    for ext in ["commands.general", "commands.accounts", "commands.scheduler", "commands.admin"]:
        try:
            await bot.load_extension(ext)
            print(f"Loaded {ext}")
        except Exception as e:
            print(f"FAILED to load {ext}: {e}")


# Python 3.10+ recommended entrypoint
async def main():
    async with bot:
        await load_cogs()
        await bot.start(BOT_KEY)

import asyncio
asyncio.run(main())

