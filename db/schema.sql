PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
  discord_user_id TEXT PRIMARY KEY,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS riot_accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  discord_user_id TEXT NOT NULL,
  puuid TEXT NOT NULL UNIQUE,
  riot_id TEXT,
  platform TEXT,
  added_at INTEGER NOT NULL,
  FOREIGN KEY (discord_user_id)
    REFERENCES users(discord_user_id)
    ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS guild_settings (
  guild_id TEXT PRIMARY KEY,
  leaderboard_channel_id TEXT,
  leaderboard_message_id TEXT,
  season_start_ts INTEGER,
  season_key TEXT
);


CREATE INDEX IF NOT EXISTS idx_riot_accounts_user
  ON riot_accounts(discord_user_id);