CREATE TABLE IF NOT EXISTS spot_inventory_stackable (
    spot_id INTEGER NOT NULL REFERENCES spot(spot_id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES item(item_id) ON DELETE CASCADE,
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    PRIMARY KEY (spot_id, item_id)
);

CREATE INDEX IF NOT EXISTS idx_spot_inventory_stackable_spot_id ON spot_inventory_stackable(spot_id);
CREATE INDEX IF NOT EXISTS idx_spot_inventory_stackable_item_id ON spot_inventory_stackable(item_id);