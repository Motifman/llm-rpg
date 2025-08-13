CREATE TABLE IF NOT EXISTS guild_member (
    guild_id INTEGER NOT NULL REFERENCES guild(guild_id) ON DELETE CASCADE,
    player_id INTEGER NOT NULL REFERENCES player(player_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('leader', 'member')),
    rank INTEGER NOT NULL CHECK (rank >= 0),
    reputation INTEGER NOT NULL CHECK (reputation >= 0),
    quest_completed_count INTEGER NOT NULL CHECK (quest_completed_count >= 0),
    total_earn_gold INTEGER NOT NULL CHECK (total_earn_gold >= 0),
    joined_at INTEGER NOT NULL,
    PRIMARY KEY (guild_id, player_id)
);
CREATE INDEX IF NOT EXISTS idx_guild_member_guild_id ON guild_member(guild_id);
CREATE INDEX IF NOT EXISTS idx_guild_member_player_id ON guild_member(player_id);