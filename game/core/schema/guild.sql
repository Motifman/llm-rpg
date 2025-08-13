CREATE TABLE IF NOT EXISTS guild (
    guild_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    location_spot_id INTEGER NOT NULL REFERENCES spot(spot_id) ON DELETE CASCADE,
    level INTEGER NOT NULL CHECK (level >= 0),
    exp INTEGER NOT NULL CHECK (exp >= 0),
    max_member INTEGER NOT NULL CHECK (max_member >= 0),
    member_count INTEGER NOT NULL CHECK (member_count >= 0),
    fee_rate FLOAT NOT NULL CHECK (fee_rate >= 0),
    created_at INTEGER NOT NULL
    UNIQUE (location_spot_id)
);
CREATE INDEX IF NOT EXISTS idx_guild_location_spot_id ON guild(location_spot_id);