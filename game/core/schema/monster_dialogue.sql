CREATE TABLE IF NOT EXISTS monster_dialogue (
    dialogue_id INTEGER PRIMARY KEY AUTOINCREMENT,
    monster_id INTEGER NOT NULL REFERENCES monster(monster_id) ON DELETE CASCADE,
    dialogue_type TEXT NOT NULL CHECK (dialogue_type IN ('greeting', 'attack', 'defend', 'death', 'victory', 'escape')),
    text TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_monster_dialogue_monster_id ON monster_dialogue(monster_id);