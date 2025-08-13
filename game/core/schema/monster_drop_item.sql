CREATE TABLE IF NOT EXISTS monster_drop_item (
    monster_id INTEGER NOT NULL REFERENCES monster(monster_id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES item(item_id) ON DELETE CASCADE,
    drop_rate FLOAT NOT NULL CHECK (drop_rate >= 0),
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    PRIMARY KEY (monster_id, item_id)
);

CREATE INDEX IF NOT EXISTS idx_monster_drop_item_monster_id ON monster_drop_item(monster_id);