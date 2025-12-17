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
  season_key TEXT,

  refresh_weekday INTEGER NOT NULL DEFAULT 0,
  refresh_hour INTEGER NOT NULL DEFAULT 9,
  refresh_minute INTEGER NOT NULL DEFAULT 0,
  refresh_tz TEXT NOT NULL DEFAULT 'Europe/Copenhagen',
  next_refresh_ts INTEGER,
  last_refresh_ts INTEGER
);



CREATE TABLE IF NOT EXISTS account_stats (
  account_id INTEGER PRIMARY KEY,
  season_key TEXT NOT NULL,
  games_played INTEGER NOT NULL,
  last_updated INTEGER NOT NULL,
  FOREIGN KEY (account_id)
    REFERENCES riot_accounts(id)
    ON DELETE CASCADE
);



CREATE INDEX IF NOT EXISTS idx_riot_accounts_user
  ON riot_accounts(discord_user_id);