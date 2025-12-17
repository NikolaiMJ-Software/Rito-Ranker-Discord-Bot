import discord
import db

MAX_ROWS = 25

async def refresh_leaderboard_for_guild(bot: discord.Client, guild_id: int) -> None:
    gs = await db.get_guild_settings(guild_id)
    channel_id = gs["leaderboard_channel_id"]
    message_id = gs["leaderboard_message_id"]
    season_key = gs["season_key"] or "default"

    if not channel_id or not message_id:
        # Not configured yet
        return

    guild = bot.get_guild(int(guild_id))
    if guild is None:
        return

    channel = guild.get_channel(int(channel_id))
    if channel is None:
        return

    try:
        msg = await channel.fetch_message(int(message_id))
    except Exception:
        return

    # Build leaderboard based on current guild members only
    member_ids = {str(m.id) for m in guild.members}

    rows = await db.get_guild_leaderboard_rows(
        guild_member_ids=list(member_ids),
        season_key=season_key
    )

    # rows: list of (discord_user_id, games_played_total)
    rows = sorted(rows, key=lambda r: r[1], reverse=True)

    lines = []
    for i, (duid, total) in enumerate(rows[:MAX_ROWS], start=1):
        lines.append(f"**{i}.** <@{duid}> — **{total}** games")

    if not lines:
        lines = ["No data yet. Users must /link and stats must be updated."]

    content = (
        f"📊 **League Games Leaderboard**\n"
        f"Season: `{season_key}`\n\n"
        + "\n".join(lines)
    )

    await msg.edit(content=content)
