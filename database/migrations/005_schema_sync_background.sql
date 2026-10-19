-- ============================================================================
-- MM.AI - Migration 005 : Schema Sync - colonnes BACKGROUND
-- Version : 3.1
-- Date    : 2026-05-12
--
-- Aligne fighters sur tables finales - fighters.csv (v3.1 / 66 colonnes) :
--   * Suppression sport_avant  (etait prior_sport dans le CSV)
--   * Suppression specialite   (etait specialty dans le CSV)
--   * Renommage style_primaire -> first_sport (etait primary_style dans le CSV)
--
-- Sans risque de perte : sport_avant et specialite etaient rarement remplis.
-- Verifier avec le SELECT ci-dessous avant d'executer si doute.
-- ============================================================================

-- Optionnel : voir si des donnees seraient perdues
-- SELECT name, sport_avant, specialite, style_primaire
-- FROM fighters
-- WHERE sport_avant IS NOT NULL OR specialite IS NOT NULL OR style_primaire IS NOT NULL;

BEGIN;

-- Renommage avant suppression (pour ne pas perdre style_primaire si rempli)
ALTER TABLE fighters RENAME COLUMN style_primaire TO first_sport;

-- Suppression des colonnes retirees du schema CSV
ALTER TABLE fighters DROP COLUMN IF EXISTS sport_avant;
ALTER TABLE fighters DROP COLUMN IF EXISTS specialite;

COMMIT;

-- Verification post-migration
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name   = 'fighters'
  AND column_name  IN ('first_sport', 'sport_avant', 'specialite', 'style_primaire')
ORDER BY column_name;
-- Resultat attendu : 1 ligne uniquement (first_sport, character varying)
