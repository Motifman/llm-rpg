CREATE TABLE IF NOT EXISTS players (
  player_id  TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  role       TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
