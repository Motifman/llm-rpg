CREATE TABLE IF NOT EXISTS monster (
    monster_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    max_hp INTEGER NOT NULL CHECK (max_hp >= 0),
    max_mp INTEGER NOT NULL CHECK (max_mp >= 0),
    attack INTEGER NOT NULL CHECK (attack >= 0),
    defense INTEGER NOT NULL CHECK (defense >= 0),
    speed INTEGER NOT NULL CHECK (speed >= 0),
    critical_rate FLOAT NOT NULL CHECK (critical_rate >= 0),
    evasion_rate FLOAT NOT NULL CHECK (evasion_rate >= 0),
    exp_drop INTEGER NOT NULL CHECK (exp_drop >= 0),
    gold_drop INTEGER NOT NULL CHECK (gold_drop >= 0)
);

CREATE INDEX IF NOT EXISTS idx_monster_name ON monster(name);