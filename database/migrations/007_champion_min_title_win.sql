-- ============================================================================
-- MM.AI - Migration 007 : garde-fou ufc_title_match_win >= 1 pour champions
-- Version : 3.2
-- Date    : 2026-05-20
--
-- CONTEXTE :
--   La migration 006 a renomme defenses -> match_win et bumpe +1 les champions
--   au moment de l'execution. Mais les fighters insérés APRES la migration 006
--   (ex: Joshua Van, scrape sans URL FightMatrix) ont ufc_title_match_win = 0
--   alors qu'ils sont is_ufc_champion = TRUE.
--
--   Logique : un champion a forcement gagne au moins le combat ou il a pris
--   la ceinture → match_win >= 1 est une invariante de la BDD.
--
-- ACTION :
--   Pour tout fighter is_ufc_champion = TRUE ayant match_win < 1 → set 1.
--   Le vrai compte (prise + defenses) sera recupere au prochain scrape avec FM
--   via ALWAYS_REFRESH (ajoute dans scrape_mma.py meme commit).
-- ============================================================================

BEGIN;

UPDATE fighters
SET ufc_title_match_win = 1
WHERE is_ufc_champion = TRUE
  AND (ufc_title_match_win IS NULL OR ufc_title_match_win < 1);

DO $$
DECLARE
    n_fixed INT;
BEGIN
    SELECT COUNT(*) INTO n_fixed
    FROM fighters
    WHERE is_ufc_champion = TRUE
      AND ufc_title_match_win >= 1;
    RAISE NOTICE 'Migration 007 OK : % champions ont match_win >= 1', n_fixed;
END $$;

COMMIT;
