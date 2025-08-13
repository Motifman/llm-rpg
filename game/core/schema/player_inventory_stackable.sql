CREATE TABLE IF NOT EXISTS player_inventory_stackable (
  player_id INTEGER NOT NULL REFERENCES player(player_id) ON DELETE CASCADE,
  item_id   INTEGER NOT NULL REFERENCES item(item_id) ON DELETE CASCADE,
  count     INTEGER NOT NULL CHECK (count >= 0),
  PRIMARY KEY (player_id, item_id)
);
CREATE INDEX IF NOT EXISTS idx_inv_player ON player_inventory_stackable(player_id);