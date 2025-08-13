CREATE TABLE IF NOT EXISTS quest (
    quest_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    quest_type TEXT NOT NULL CHECK (quest_type IN ('monster_hunt', 'item_collection', 'exploration', 'delivery', 'rescue', 'custom')),
    difficulty TEXT NOT NULL CHECK (difficulty IN ('E', 'D', 'C', 'B', 'A', 'S')),
    client_id INTEGER NOT NULL REFERENCES player(player_id) ON DELETE CASCADE,
    guild_id INTEGER NOT NULL REFERENCES guild(guild_id) ON DELETE CASCADE,
    reward_gold INTEGER NOT NULL CHECK (reward_gold >= 0),
    reward_exp INTEGER NOT NULL CHECK (reward_exp >= 0),
    status TEXT NOT NULL CHECK (status IN ('available', 'accepted', 'in_progress', 'completed', 'failed', 'cancelled')),
    accepted_by INTEGER NOT NULL REFERENCES player(player_id) ON DELETE CASCADE,
    accepted_at INTEGER NOT NULL,
    deadline INTEGER DEFAULT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_quest_client_id ON quest(client_id);
CREATE INDEX IF NOT EXISTS idx_quest_guild_id ON quest(guild_id);
CREATE INDEX IF NOT EXISTS idx_quest_status ON quest(status);
CREATE INDEX IF NOT EXISTS idx_quest_accepted_by ON quest(accepted_by);
CREATE INDEX IF NOT EXISTS idx_quest_deadline ON quest(deadline);
CREATE INDEX IF NOT EXISTS idx_quest_created_at ON quest(created_at);