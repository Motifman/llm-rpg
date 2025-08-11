CREATE TABLE IF NOT EXISTS player_appearance (
  player_id TEXT NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
  slot      TEXT NOT NULL,
  value     TEXT NOT NULL,
  PRIMARY KEY (player_id, slot)
);
