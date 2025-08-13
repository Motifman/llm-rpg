CREATE TABLE IF NOT EXISTS quest_condition (
    condition_id INTEGER PRIMARY KEY AUTOINCREMENT,
    quest_id INTEGER NOT NULL REFERENCES quest(quest_id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    condition_type TEXT NOT NULL CHECK (condition_type IN ('kill_monster', 'collect_item', 'reach_location', 'deliver_item', 'rescue_npc', 'custom')),
    target_id INTEGER NOT NULL,
    required_count INTEGER NOT NULL DEFAULT 0 CHECK (required_count >= 0),
    current_count INTEGER NOT NULL DEFAULT 0 CHECK (current_count >= 0),
    is_completed INTEGER NOT NULL DEFAULT 0 CHECK (is_completed IN (0, 1)),
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_quest_condition_quest_id ON quest_condition(quest_id);