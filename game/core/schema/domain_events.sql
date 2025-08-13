CREATE TABLE IF NOT EXISTS domain_events (
  event_id     TEXT PRIMARY KEY,
  event_type   TEXT NOT NULL,
  aggregate_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at   INTEGER NOT NULL,
  processed_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_domain_events_unprocessed
  ON domain_events(processed_at) WHERE processed_at IS NULL;
