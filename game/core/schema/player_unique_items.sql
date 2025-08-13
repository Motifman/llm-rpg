CREATE TABLE IF NOT EXISTS player_unique_items (
  unique_item_id TEXT PRIMARY KEY,
  player_id      TEXT NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
  item_id        TEXT NOT NULL,
  durability     INTEGER,
  rarity         TEXT,
  meta_json      TEXT
);
CREATE INDEX IF NOT EXISTS idx_unique_items_player ON player_unique_items(player_id);
