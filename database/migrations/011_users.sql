-- 011_users.sql
-- Table users — authentification, vérification email, tier free/premium.
-- Idempotente, safe to re-run.

CREATE TABLE IF NOT EXISTS users (
    id                          SERIAL PRIMARY KEY,
    pseudo                      TEXT        NOT NULL UNIQUE,
    first_name                  TEXT        NOT NULL,
    last_name                   TEXT        NOT NULL,
    age                         INTEGER     NOT NULL CHECK (age >= 13 AND age <= 120),
    email                       TEXT        NOT NULL UNIQUE,
    password_hash               TEXT        NOT NULL,

    -- Email verification (strict gate : pas de login tant que email_verified = FALSE)
    email_verified              BOOLEAN     NOT NULL DEFAULT FALSE,
    verification_token          TEXT,
    verification_expires_at     TIMESTAMPTZ,

    -- Tier (free par défaut, premium déverrouille Scouter calculate / Compare / Matchmaking)
    tier                        TEXT        NOT NULL DEFAULT 'free'
                                            CHECK (tier IN ('free', 'premium')),
    stripe_customer_id          TEXT        UNIQUE,
    premium_until               TIMESTAMPTZ,

    -- Timestamps
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at               TIMESTAMPTZ
);

-- Indexes pour les lookups fréquents (login par email ou pseudo, lookup par token)
CREATE INDEX IF NOT EXISTS idx_users_email             ON users (LOWER(email));
CREATE INDEX IF NOT EXISTS idx_users_pseudo            ON users (LOWER(pseudo));
CREATE INDEX IF NOT EXISTS idx_users_verification_tok  ON users (verification_token)
    WHERE verification_token IS NOT NULL;

-- Trigger updated_at automatique
CREATE OR REPLACE FUNCTION trg_users_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS users_updated_at ON users;
CREATE TRIGGER users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION trg_users_updated_at();
