-- 010_events_tables.sql
-- Tables events + event_fights — idempotentes, safe to re-run.

CREATE TABLE IF NOT EXISTS events (
    id              SERIAL PRIMARY KEY,
    name            TEXT        NOT NULL,
    slug            TEXT,
    promotion       TEXT,
    date            DATE,
    venue           TEXT,
    city            TEXT,
    country         TEXT,
    tapology_url    TEXT        UNIQUE,
    status          TEXT        NOT NULL DEFAULT 'completed',  -- completed | upcoming | cancelled
    awards          JSONB       NOT NULL DEFAULT '[]'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS event_fights (
    id              SERIAL  PRIMARY KEY,
    event_id        INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    card_section    TEXT    NOT NULL DEFAULT 'Main Card',
    bout_order      INTEGER NOT NULL DEFAULT 0,
    fighter1_id     INTEGER REFERENCES fighters(id),
    fighter2_id     INTEGER REFERENCES fighters(id),
    fighter1_name   TEXT    NOT NULL,
    fighter2_name   TEXT    NOT NULL,
    weight_class    TEXT,
    is_title_fight  BOOLEAN NOT NULL DEFAULT FALSE,
    winner_id       INTEGER REFERENCES fighters(id),
    winner_name     TEXT,
    method          TEXT,
    method_detail   TEXT,
    round_num       INTEGER,
    time_str        TEXT,
    status          TEXT    NOT NULL DEFAULT 'completed',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_event_fights_event_id ON event_fights(event_id);
CREATE INDEX IF NOT EXISTS idx_event_fights_f1       ON event_fights(fighter1_id);
CREATE INDEX IF NOT EXISTS idx_event_fights_f2       ON event_fights(fighter2_id);
CREATE INDEX IF NOT EXISTS idx_events_date           ON events(date DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_events_promotion      ON events(promotion);
CREATE INDEX IF NOT EXISTS idx_events_status         ON events(status);
