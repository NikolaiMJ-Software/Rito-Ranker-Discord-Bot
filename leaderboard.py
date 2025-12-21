import discord
import db

MAX_ROWS = 25
MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}

def _move_icon(prev_rank: int | None, new_rank: int) -> str:
    if prev_rank is None:
        return "🆕"
    if new_rank < prev_rank:
        return "⬆️"
    if new_rank > prev_rank:
        return "⬇️"
    return "➖"

def _rank_prefix(rank: int) -> str:
    return MEDALS.get(rank, f"**{rank}.**")

def _format_row(rank: int, duid: str, total: int, prev_rank: int | None, prev_games: int | None) -> str:
    move = _move_icon(prev_rank, rank)

    gained = ""
    if prev_games is not None:
        diff = total - prev_games
        if diff > 0:
            gained = f" `(+{diff})`"
        elif diff < 0:
            gained = f" `({diff})`"

    return f"{_rank_prefix(rank)} {move} <@{duid}> — **{total}**{gained}"

def _dense_rank(sorted_rows: list[tuple[str, int]]) -> list[tuple[int, str, int]]:
    """
    Dense ranking:
      26, 26, 25 => ranks 1, 1, 2
    Input must already be sorted by total desc (and stable tie-break).
    """
    out: list[tuple[int, str, int]] = []
    prev_score: int | None = None
    rank = 0

    for duid, total in sorted_rows:
        if prev_score is None or total != prev_score:
            rank += 1
            prev_score = total
        out.append((rank, duid, total))

    return out

async def refresh_leaderboard_for_guild(bot: discord.Client, guild_id: int, window_key: str) -> None:
    gs = await db.get_guild_settings(guild_id)
    channel_id = gs.get("leaderboard_channel_id")
    message_id = gs.get("leaderboard_message_id")

    if not channel_id or not message_id:
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

    member_ids = {str(m.id) for m in guild.members}

    rows = await db.get_guild_leaderboard_rows(
        guild_member_ids=list(member_ids),
        window_key=window_key,
    )

    # Stable sorting:
    #  - total desc
    #  - user id asc to prevent ties swapping between refreshes
    rows = sorted(rows, key=lambda r: (-r[1], int(r[0])))[:MAX_ROWS]

    prev = await db.get_snapshot_map(guild_id, window_key)

    queue_policy_label = (gs.get("queue_policy") or "all").replace("_", " ").title()
    window_mode = gs.get("window_mode", "month")

    embed = discord.Embed(
        title="📊 League Games Leaderboard",
        description=(
            f"Window: `{window_mode}`\n"
            f"Queues: **{queue_policy_label}** (LoL only, no TFT)"
        ),
        color=discord.Color.gold(),
    )

    # Thumbnail
    if rows:
        top_user_id = int(rows[0][0])
        top_member = guild.get_member(top_user_id)
        if top_member and top_member.avatar:
            embed.set_thumbnail(url=top_member.avatar.url)
        elif guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
    elif guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    if not rows:
        embed.add_field(
            name="No data yet",
            value="Users must `/link` and stats must be updated.",
            inline=False,
        )
        await msg.edit(content=None, embed=embed)
        return

    ranked_rows = _dense_rank(rows)

    formatted: list[str] = []
    for rank, duid, total in ranked_rows:
        prev_rank, prev_games = prev.get(duid, (None, None))
        formatted.append(_format_row(rank, duid, total, prev_rank, prev_games))

        # snapshot uses the dense rank too (important!)
        await db.upsert_snapshot_row(guild_id, window_key, duid, rank, total)

    embed.add_field(name="🏆 Podium", value="\n".join(formatted[:3]), inline=False)

    rest = formatted[3:]
    if rest:
        split = (len(rest) + 1) // 2
        embed.add_field(name="📋 Ranks", value="\n".join(rest[:split]) or "—", inline=True)
        embed.add_field(name="\u200b", value="\n".join(rest[split:]) or "—", inline=True)

    last_ts = gs.get("last_refresh_ts")
    embed.add_field(
        name="🕒 Last updated",
        value=(f"<t:{last_ts}:R> ( <t:{last_ts}:F> )" if last_ts else "—"),
        inline=False,
    )

    embed.set_footer(text="🆕 new | ⬆️ up | ⬇️ down | ➖ same")
    await msg.edit(content=None, embed=embed)
