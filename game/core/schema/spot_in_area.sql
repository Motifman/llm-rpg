CREATE TABLE IF NOT EXISTS spot_in_area (
    area_id INTEGER NOT NULL REFERENCES area(area_id) ON DELETE CASCADE,
    spot_id INTEGER NOT NULL REFERENCES spot(spot_id) ON DELETE CASCADE,
    PRIMARY KEY (area_id, spot_id)
);

CREATE INDEX IF NOT EXISTS idx_spot_in_area_spot_id ON spot_in_area(spot_id);