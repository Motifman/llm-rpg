CREATE TABLE IF NOT EXISTS item (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    price INTEGER NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('weapon', 'helmet', 'chest', 'legs', 'boots', 'gloves', 'consumable', 'material', 'quest', 'other')),
    rarity TEXT NOT NULL CHECK (rarity IN ('common', 'uncommon', 'rare', 'epic', 'legendary', 'mythic')),
    created_at INTEGER NOT NULL
);
