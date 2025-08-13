CREATE TABLE IF NOT EXISTS player_equipment (
  player_id      INTEGER NOT NULL REFERENCES player(player_id) ON DELETE CASCADE,
  slot           TEXT NOT NULL CHECK (slot IN ('weapon', 'helmet', 'chest', 'legs', 'boots', 'gloves')),
  unique_item_id INTEGER NOT NULL REFERENCES item_unique(unique_item_id) ON DELETE CASCADE,
  PRIMARY KEY (player_id, slot)
);
CREATE INDEX IF NOT EXISTS idx_equipment_unique ON player_equipment(unique_item_id);
