CREATE TABLE IF NOT EXISTS spot_inventory_unique (
    spot_id INTEGER NOT NULL REFERENCES spot(spot_id) ON DELETE CASCADE,
    unique_item_id INTEGER NOT NULL REFERENCES item_unique(unique_item_id) ON DELETE CASCADE,
    PRIMARY KEY (spot_id, unique_item_id)
);

CREATE INDEX IF NOT EXISTS idx_spot_inventory_unique_spot_id ON spot_inventory_unique(spot_id);
CREATE INDEX IF NOT EXISTS idx_spot_inventory_unique_unique_item_id ON spot_inventory_unique(unique_item_id);