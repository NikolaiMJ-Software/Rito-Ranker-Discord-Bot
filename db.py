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
