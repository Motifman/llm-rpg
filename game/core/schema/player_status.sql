CREATE TABLE IF NOT EXISTS player_status (
  player_id  TEXT PRIMARY KEY REFERENCES players(player_id) ON DELETE CASCADE,
  hp         INTEGER NOT NULL CHECK (hp >= 0),
  mp         INTEGER NOT NULL CHECK (mp >= 0),
  level      INTEGER NOT NULL CHECK (level >= 1),
  experience INTEGER NOT NULL CHECK (experience >= 0),
  gold       INTEGER NOT NULL CHECK (gold >= 0),
  attack     INTEGER NOT NULL DEFAULT 10 CHECK (attack >= 0),
  defense    INTEGER NOT NULL DEFAULT 10 CHECK (defense >= 0),
  speed      INTEGER NOT NULL DEFAULT 10 CHECK (speed >= 0),
  max_hp     INTEGER NOT NULL DEFAULT 100 CHECK (max_hp >= 0),
  max_mp     INTEGER NOT NULL DEFAULT 100 CHECK (max_mp >= 0)
);
