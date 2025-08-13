CREATE TABLE IF NOT EXISTS player (
  player_id  INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT NOT NULL UNIQUE,
  role       TEXT NOT NULL,
  hp         INTEGER NOT NULL CHECK (hp >= 0),
  mp         INTEGER NOT NULL CHECK (mp >= 0),
  level      INTEGER NOT NULL DEFAULT 1 CHECK (level >= 1),
  experience INTEGER NOT NULL DEFAULT 0 CHECK (experience >= 0),
  gold       INTEGER NOT NULL DEFAULT 0 CHECK (gold >= 0),
  attack     INTEGER NOT NULL CHECK (attack >= 0),
  defense    INTEGER NOT NULL CHECK (defense >= 0),
  speed      INTEGER NOT NULL CHECK (speed >= 0),
  max_hp     INTEGER NOT NULL CHECK (max_hp >= 0),
  max_mp     INTEGER NOT NULL CHECK (max_mp >= 0),
  state      TEXT NOT NULL CHECK (state IN ('idle', 'walking', 'fighting', 'dead')),
  current_spot_id INTEGER NOT NULL REFERENCES spot(spot_id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL
);
