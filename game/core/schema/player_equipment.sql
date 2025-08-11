CREATE TABLE IF NOT EXISTS player_equipment (
  player_id      TEXT NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
  slot           TEXT NOT NULL,
  item_id        TEXT,
  unique_item_id TEXT,
  PRIMARY KEY (player_id, slot),
  CHECK ((item_id IS NOT NULL) <> (unique_item_id IS NOT NULL)),
  FOREIGN KEY (unique_item_id) REFERENCES player_unique_items(unique_item_id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_equipment_unique ON player_equipment(unique_item_id);
