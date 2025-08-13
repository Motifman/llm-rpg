CREATE TABLE IF NOT EXISTS quest_reward_item (
    quest_id INTEGER NOT NULL REFERENCES quest(quest_id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES item(item_id) ON DELETE CASCADE,
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    PRIMARY KEY (quest_id, item_id)
);
CREATE INDEX IF NOT EXISTS idx_quest_reward_item_quest_id ON quest_reward_item(quest_id);
CREATE INDEX IF NOT EXISTS idx_quest_reward_item_item_id ON quest_reward_item(item_id);