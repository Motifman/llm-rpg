CREATE TABLE IF NOT EXISTS monster_instance (
    monster_instance_id INTEGER PRIMARY KEY AUTOINCREMENT,
    monster_id INTEGER NOT NULL REFERENCES monster(monster_id) ON DELEGTE CASCADE,
    current_spot_id INTEGER NOT NULL REFERENCES spot(spot_id) ON DELETE CASCADE,
    current_hp INTEGER NOT NULL CHECK (current_hp >= 0),
    current_mp INTEGER NOT NULL CHECK (current_mp >= 0),
    is_alive INTEGER NOT NULL DEFAULT 1 CHECK (is_alive IN (0, 1)),
    is_hidden INTEGER NOT NULL DEFAULT 0 CHECK (is_hidden IN (0, 1)),
    locked_by_battle_id INTEGER REFERENCES battle(battle_id) ON DELETE SET NULL,
    version INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_monster_instance_monster_id ON monster_instance(monster_id);
CREATE INDEX IF NOT EXISTS idx_monster_instance_current_spot_id ON monster_instance(current_spot_id);