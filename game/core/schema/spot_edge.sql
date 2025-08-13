CREATE TABLE IF NOT EXISTS spot_edge (
    from_spot_id INTEGER NOT NULL REFERENCES spot(spot_id) ON DELETE CASCADE,
    to_spot_id INTEGER NOT NULL REFERENCES spot(spot_id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    PRIMARY KEY (from_spot_id, to_spot_id)
);

CREATE INDEX IF NOT EXISTS idx_spot_edge_from_spot_id ON spot_edge(from_spot_id);
CREATE INDEX IF NOT EXISTS idx_spot_edge_to_spot_id ON spot_edge(to_spot_id);
CREATE INDEX IF NOT EXISTS idx_spot_edge_from_spot_id_to_spot_id ON spot_edge(from_spot_id, to_spot_id);