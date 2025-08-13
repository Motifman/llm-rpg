CREATE TABLE IF NOT EXISTS player_inventory_unique (
    player_id INTEGER NOT NULL REFERENCES player(player_id) ON DELETE CASCADE,
    unique_item_id INTEGER NOT NULL REFERENCES item_unique(unique_item_id) ON DELETE CASCADE,
    PRIMARY KEY (unique_item_id)  -- 同じアイテムが複数プレイヤーに保持されることを防ぐ
);
CREATE INDEX IF NOT EXISTS idx_inv_player ON player_inventory_unique(player_id);