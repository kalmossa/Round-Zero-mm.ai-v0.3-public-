-- Migration 013 : avatar_data on users + reports table
-- Idempotent (IF NOT EXISTS / safe re-run)

-- Avatar data URL (base64, max ~256 KB) stored directly on the user row
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_data TEXT;

-- Reports table (fighter/event issue reports from users and visitors)
CREATE TABLE IF NOT EXISTS reports (
    id          SERIAL PRIMARY KEY,
    fighter_id  INT REFERENCES fighters(id) ON DELETE SET NULL,
    event_id    INT,
    report_type VARCHAR(50) NOT NULL DEFAULT 'other',
    message     TEXT,
    ip_address  TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS reports_fighter_id_idx ON reports (fighter_id);
CREATE INDEX IF NOT EXISTS reports_created_at_idx ON reports (created_at DESC);
