CREATE TABLE IF NOT EXISTS player_location (
  player_id  TEXT PRIMARY KEY REFERENCES players(player_id) ON DELETE CASCADE,
  spot_id    TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_location_spot ON player_location(spot_id);
