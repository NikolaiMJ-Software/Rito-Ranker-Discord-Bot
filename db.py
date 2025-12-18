from __future__ import annotations

import time
from pathlib import Path
from typing import Iterable, List, Tuple, Optional

import aiosqlite

#define db pathing
DB_DIR = Path("db")
DB_PATH = DB_DIR / "leaguebot.sqlite3"
SCHEMA_PATH = DB_DIR / "schema.sql"

#function for time conversion
def _now_ts() -> int:
    return int(time.time())

#Ensures db exists, if not create the db
async def init_db() -> None:
    """
    Ensures db folder exists, creates DB file if missing, and applies schema.sql.
    Safe to call on every startup.
    """
    DB_DIR.mkdir(parents=True, exist_ok=True)
    #if schema paths does not exist, insert the schemas from schema.sql
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Missing schema file: {SCHEMA_PATH}")

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")

    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(schema_sql)
        await db.commit()

#Insertion of users function
async def upsert_user(discord_user_id: int) -> None:
    """
    Inserts the user row if it doesn't exist yet.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users(discord_user_id, created_at) VALUES(?, ?)",
            (str(discord_user_id), _now_ts()),
        )
        await db.commit()

#Function to link riot accounts to discord accounts
async def add_riot_account(
    discord_user_id: int,
    puuid: str,
    riot_id: Optional[str] = None,
    platform: Optional[str] = None,
) -> bool:
    """
    Links a Riot account to a Discord user.
    Returns True if inserted, False if already exists (by UNIQUE puuid).
    """
    await upsert_user(discord_user_id)

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                INSERT INTO riot_accounts(discord_user_id, puuid, riot_id, platform, added_at)
                VALUES(?, ?, ?, ?, ?)
                """,
                (str(discord_user_id), puuid, riot_id, platform, _now_ts()),
            )
            await db.commit()
        return True
    except aiosqlite.IntegrityError:
        # Most likely: puuid already linked (UNIQUE)
        return False

#Collect riot account data and display it
async def list_riot_accounts(discord_user_id: int) -> List[Tuple[int, str, Optional[str], Optional[str]]]:
    """
    Returns a list of (id, puuid, riot_id, platform) for the Discord user.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT id, puuid, riot_id, platform
            FROM riot_accounts
            WHERE discord_user_id = ?
            ORDER BY added_at ASC
            """,
            (str(discord_user_id),),
        )
        rows = await cur.fetchall()
        return rows


async def remove_riot_account(discord_user_id: int, account_id: int) -> int:
    """
    Removes a linked Riot account by its internal riot_accounts.id.
    Returns number of rows deleted (0 or 1).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM riot_accounts WHERE discord_user_id = ? AND id = ?",
            (str(discord_user_id), account_id),
        )
        await db.commit()
        return cur.rowcount


async def remove_riot_account_by_riot_id(discord_user_id: int, riot_id: str, platform: str) -> int:
    """
    Removes a linked Riot account by Riot ID + platform for a given Discord user.
    Returns number of rows deleted (0..n).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            DELETE FROM riot_accounts
            WHERE discord_user_id = ?
              AND riot_id = ?
              AND platform = ?
            """,
            (str(discord_user_id), riot_id.strip(), platform.strip().upper()),
        )
        await db.commit()
        return cur.rowcount


async def remove_riot_account_by_puuid(discord_user_id: int, puuid: str) -> int:
    """
    Removes a linked Riot account by PUUID for a given Discord user.
    Returns number of rows deleted (0..n).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            DELETE FROM riot_accounts
            WHERE discord_user_id = ?
              AND puuid = ?
            """,
            (str(discord_user_id), puuid),
        )
        await db.commit()
        return cur.rowcount


async def ensure_guild_settings(guild_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT OR IGNORE INTO guild_settings(guild_id) VALUES(?)",
            (str(guild_id),)
        )
        await conn.commit()

async def get_guild_settings(guild_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM guild_settings WHERE guild_id = ?", (str(guild_id),))
        row = await cur.fetchone()
        return dict(row) if row else {}

async def set_leaderboard_message(guild_id: int, channel_id: int, message_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """
            UPDATE guild_settings
            SET leaderboard_channel_id = ?, leaderboard_message_id = ?
            WHERE guild_id = ?
            """,
            (str(channel_id), str(message_id), str(guild_id)),
        )
        await conn.commit()

async def set_refresh_schedule(guild_id: int, refresh_weekday: int, refresh_hour: int, refresh_minute: int,
                              refresh_tz: str, next_refresh_ts: int) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """
            UPDATE guild_settings
            SET refresh_weekday=?, refresh_hour=?, refresh_minute=?, refresh_tz=?, next_refresh_ts=?
            WHERE guild_id=?
            """,
            (refresh_weekday, refresh_hour, refresh_minute, refresh_tz, next_refresh_ts, str(guild_id)),
        )
        await conn.commit()

async def set_next_refresh_ts(guild_id: int, next_ts: int) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE guild_settings SET next_refresh_ts=? WHERE guild_id=?",
            (next_ts, str(guild_id)),
        )
        await conn.commit()

async def set_last_refresh_ts(guild_id: int, last_ts: int) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE guild_settings SET last_refresh_ts=? WHERE guild_id=?",
            (last_ts, str(guild_id)),
        )
        await conn.commit()

async def list_guild_refresh_due(now_ts: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """
            SELECT *
            FROM guild_settings
            WHERE next_refresh_ts IS NOT NULL
              AND next_refresh_ts <= ?
            """,
            (now_ts,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

async def get_guild_leaderboard_rows(guild_member_ids: list[str], window_key: str) -> list[tuple[str, int]]:
    if not guild_member_ids:
        return []

    placeholders = ",".join("?" for _ in guild_member_ids)
    sql = f"""
    SELECT ra.discord_user_id,
           COALESCE(SUM(s.games_played), 0) AS total_games
    FROM riot_accounts ra
    LEFT JOIN account_stats s
      ON s.account_id = ra.id
     AND s.window_key = ?
    WHERE ra.discord_user_id IN ({placeholders})
    GROUP BY ra.discord_user_id
    ORDER BY total_games DESC
    """

    params = [window_key, *guild_member_ids]
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(sql, params)
        rows = await cur.fetchall()
        return [(r[0], int(r[1])) for r in rows]

    
    
async def upsert_account_stats(account_id: int, window_key: str, games_played: int) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """
            INSERT INTO account_stats(account_id, window_key, games_played, last_updated)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(account_id, window_key) DO UPDATE SET
                games_played=excluded.games_played,
                last_updated=excluded.last_updated
            """,
            (account_id, window_key, games_played, int(time.time())),
        )
        await conn.commit()


async def list_accounts_for_users(discord_user_ids: list[str]) -> list[tuple[int, str, str]]:
    """
    Returns list of (account_id, puuid, platform) for the given Discord user IDs.
    """
    if not discord_user_ids:
        return []

    placeholders = ",".join("?" for _ in discord_user_ids)
    sql = f"""
    SELECT id, puuid, platform
    FROM riot_accounts
    WHERE discord_user_id IN ({placeholders})
    """
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(sql, discord_user_ids)
        rows = await cur.fetchall()
        return [(int(r[0]), str(r[1]), str(r[2])) for r in rows]

async def set_window_mode(guild_id: int, mode: str, tz_name: str) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE guild_settings SET window_mode=?, window_tz=? WHERE guild_id=?",
            (mode, tz_name, str(guild_id))
        )
        await conn.commit()

async def set_window_since_ts(guild_id: int, since_ts: int) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE guild_settings SET window_since_ts=? WHERE guild_id=?",
            (since_ts, str(guild_id))
        )
        await conn.commit()

async def get_snapshot_map(guild_id: int, window_key: str) -> dict[str, tuple[int, int]]:
    """
    Returns {discord_user_id: (rank, games_played)} for previous snapshot.
    """
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """
            SELECT discord_user_id, rank, games_played
            FROM leaderboard_snapshots
            WHERE guild_id = ? AND window_key = ?
            """,
            (str(guild_id), window_key),
        )
        rows = await cur.fetchall()
        return {str(r[0]): (int(r[1]), int(r[2])) for r in rows}


async def upsert_snapshot_row(guild_id: int, window_key: str, discord_user_id: str, rank: int, games: int) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """
            INSERT INTO leaderboard_snapshots(guild_id, window_key, discord_user_id, rank, games_played, updated_at)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, window_key, discord_user_id) DO UPDATE SET
                rank=excluded.rank,
                games_played=excluded.games_played,
                updated_at=excluded.updated_at
            """,
            (str(guild_id), window_key, str(discord_user_id), rank, games, int(time.time())),
        )
        await conn.commit()


async def set_queue_policy(guild_id: int, policy: str) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE guild_settings SET queue_policy=? WHERE guild_id=?",
            (policy, str(guild_id)),
        )
        await conn.commit()


async def get_match_meta(match_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM match_meta WHERE match_id = ?",
            (match_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def upsert_match_meta(
    match_id: str,
    queue_id: int | None,
    game_mode: str | None,
    game_type: str | None,
    game_creation: int | None,
) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """
            INSERT INTO match_meta(match_id, queue_id, game_mode, game_type, game_creation, fetched_at)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id) DO UPDATE SET
              queue_id=excluded.queue_id,
              game_mode=excluded.game_mode,
              game_type=excluded.game_type,
              game_creation=excluded.game_creation,
              fetched_at=excluded.fetched_at
            """,
            (
                match_id,
                queue_id,
                game_mode,
                game_type,
                game_creation,
                int(time.time()),
            ),
        )
        await conn.commit()
