-- 022_reports_status.sql
-- Ajoute le suivi d'etat aux signalements (table reports) pour le panel admin.
-- La table reports est creee a la volee par api/auth.py (CREATE TABLE IF NOT EXISTS)
-- sans colonne d'etat -> on l'ajoute ici. Idempotente, safe to re-run.

CREATE TABLE IF NOT EXISTS reports (
    id          SERIAL PRIMARY KEY,
    fighter_id  INT REFERENCES fighters(id) ON DELETE SET NULL,
    event_id    INT,
    report_type VARCHAR(50) NOT NULL,
    message     TEXT,
    ip_address  TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 'open' (a traiter) | 'resolved' (regle par l'admin). On ne supprime jamais une ligne.
ALTER TABLE reports ADD COLUMN IF NOT EXISTS status      TEXT NOT NULL DEFAULT 'open';
ALTER TABLE reports ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_reports_status ON reports (status);
