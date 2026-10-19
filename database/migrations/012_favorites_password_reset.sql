-- 012_favorites_password_reset.sql
-- Favoris utilisateurs + reset de mot de passe + tracking changement pseudo.
-- Idempotente, safe to re-run.

-- Favoris : table de relation user <-> fighter
CREATE TABLE IF NOT EXISTS user_favorites (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    fighter_id INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, fighter_id)
);
CREATE INDEX IF NOT EXISTS idx_favorites_user    ON user_favorites(user_id);
CREATE INDEX IF NOT EXISTS idx_favorites_fighter ON user_favorites(fighter_id);

-- Password reset tokens
ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token              TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token_expires_at   TIMESTAMPTZ;

-- Pseudo : suivi du changement unique (NULL = pas encore changé)
ALTER TABLE users ADD COLUMN IF NOT EXISTS pseudo_changed_at        TIMESTAMPTZ;

-- Index pour lookup par reset_token
CREATE INDEX IF NOT EXISTS idx_users_reset_token
    ON users(reset_token) WHERE reset_token IS NOT NULL;

-- Log
DO $$
BEGIN
    RAISE NOTICE 'Migration 012 OK : user_favorites, reset_token, pseudo_changed_at';
END $$;

COMMIT;
