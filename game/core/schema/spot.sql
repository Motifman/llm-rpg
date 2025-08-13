CREATE TABLE IF NOT EXISTS spot (
    spot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    is_entrance INTEGER NOT NULL DEFAULT 0 CHECK (is_entrance IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_spot_name ON spot(name);