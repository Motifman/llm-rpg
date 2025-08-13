CREATE TABLE IF NOT EXISTS spot_edge_condition (
    condition_id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_spot_id INTEGER NOT NULL REFERENCES spot_edge(from_spot_id) ON DELETE CASCADE,
    to_spot_id INTEGER NOT NULL REFERENCES spot_edge(to_spot_id) ON DELETE CASCADE,
    condition_type TEXT NOT NULL CHECK (condition_type IN ('min_level', 'has_item', 'check_status')),
    value1 INTEGER,
    value2 INTEGER
);
CREATE INDEX IF NOT EXISTS idx_spot_edge_condition_from_spot_id_to_spot_id ON spot_edge_condition(from_spot_id, to_spot_id);