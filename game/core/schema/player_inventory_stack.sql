CREATE TABLE IF NOT EXISTS player_inventory_stack (
  player_id TEXT NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
  item_id   TEXT NOT NULL,
  count     INTEGER NOT NULL CHECK (count >= 0),
  PRIMARY KEY (player_id, item_id)
);
CREATE INDEX IF NOT EXISTS idx_inv_player ON player_inventory_stack(player_id);
