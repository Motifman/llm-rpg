CREATE TABLE IF NOT EXISTS item_unique (
    unique_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES item(item_id) ON DELETE CASCADE,
    durability INTEGER NOT NULL CHECK (durability >= 0),
    attack INTEGER CHECK (attack >= 0), -- 武器の場合の攻撃力
    defense INTEGER CHECK (defense >= 0), -- 防具の場合の防御力
    created_at INTEGER NOT NULL
);