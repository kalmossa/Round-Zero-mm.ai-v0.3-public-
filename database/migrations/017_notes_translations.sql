-- 017_notes_translations.sql
-- Ajoute la colonne notes_translations (JSONB) pour stocker les notes
-- dans toutes les langues du site (fr, en, es, zh, pt, de, ru).
-- La colonne est remplie par le scraper via deep_translator (Google Translate)
-- lors du scrape UFC-FR, ou manuellement via translate_notes_batch.py.

ALTER TABLE fighters
    ADD COLUMN IF NOT EXISTS notes_translations JSONB DEFAULT '{}';

-- Index GIN optionnel (utile si on veut chercher dans les notes) :
-- CREATE INDEX IF NOT EXISTS idx_fighters_notes_trans ON fighters USING gin(notes_translations);

-- Vérification :
-- SELECT id, name, notes, notes_translations FROM fighters WHERE notes IS NOT NULL LIMIT 5;
