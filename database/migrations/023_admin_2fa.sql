-- 023_admin_2fa.sql
-- 2FA (TOTP) pour les comptes admin. Le secret est genere a l'enrolement
-- (scan du QR dans Google Authenticator) et n'est "actif" qu'apres confirmation
-- d'un premier code. Idempotente, safe to re-run.
--
-- Note : seuls les comptes dans ADMIN_EMAILS (.env) utilisent ces colonnes,
-- mais elles restent generiques (un user lambda les laisse a NULL/FALSE).

ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_secret  TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_enabled BOOLEAN NOT NULL DEFAULT FALSE;
