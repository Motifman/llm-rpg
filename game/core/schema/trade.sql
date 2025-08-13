CREATE TABLE IF NOT EXISTS trade(
    trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id INTEGER NOT NULL REFERENCES player(player_id) ON DELETE CASCADE,
    offered_item_id INTEGER NOT NULL REFERENCES item(item_id) ON DELETE CASCADE,
    offered_item_count INTEGER NOT NULL CHECK (offered_item_count >= 0),
    requested_gold INTEGER,
    requested_item_id INTEGER REFERENCES item(item_id) ON DELETE CASCADE,
    requested_item_count INTEGER,
    trade_type TEXT NOT NULL CHECK (trade_type IN ('global', 'direct')),
    buyer_id INTEGER DEFAULT NULL REFERENCES player(player_id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('active', 'completed', 'cancelled')),
    version INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL

    CHECK (
        (requested_gold IS NOT NULL AND requested_item_id IS NULL AND requested_item_count IS NULL)
        OR
        (requested_gold IS NULL AND requested_item_id IS NOT NULL AND requested_item_count IS NOT NULL)
    )
    CHECK (
        (trade_type = 'global' AND buyer_id IS NULL)
        OR
        (trade_type = 'direct' AND buyer_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_trade_seller_id ON trade(seller_id);
CREATE INDEX IF NOT EXISTS idx_trade_buyer_id ON trade(buyer_id);