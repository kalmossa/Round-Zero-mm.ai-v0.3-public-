-- ============================================================================
-- MM.AI - Migration 008 : ajout colonne current_league
-- Version : 3.3
-- Date    : 2026-05-20
--
-- CONTEXTE :
--   Jusqu'ici on supposait implicitement que tous les fighters etaient UFC
--   (via is_ufc_champion, ufc_official_rank, record_ufc_wins). Mais une grande
--   partie du roster vient de PFL, ONE, KSW, RIZIN, Bellator, et plein
--   d'organisations regionales (Cage Warriors, LFA, ACA, Invicta...).
--   Sans cette colonne impossible de filtrer / classer / predire correctement.
--
-- ACTION :
--   1. ALTER TABLE : ajoute la colonne (NULL autorise pour les inactifs).
--   2. Index sur la colonne (filtres frequents "donne-moi tous les PFL").
--   3. COMMENT pour documenter la convention.
--
-- VALEURS CANONIQUES (normalisees par parse_misc.detect_league_from_event) :
--   UFC, PFL, Bellator, ONE, KSW, RIZIN, Cage Warriors, ACA, ACB, LFA,
--   Invicta FC, BKFC, PRIDE, Strikeforce, WEC, DREAM, M-1, ...
--   NULL si fighter inactif (>2 ans sans combat) ou ligue non identifiable.
--
-- REVERSIBLE :
--   ALTER TABLE fighters DROP COLUMN current_league;
--   DROP INDEX idx_fighters_current_league;
-- ============================================================================

BEGIN;

ALTER TABLE fighters
    ADD COLUMN IF NOT EXISTS current_league VARCHAR(50);

COMMENT ON COLUMN fighters.current_league IS
    'Ligue/promotion actuelle (UFC, PFL, ONE, KSW, RIZIN, Bellator, ...). '
    'Derivee depuis fight_history[0].event par parse_misc.detect_league_from_event(). '
    'NULL si is_active=FALSE ou si la ligue n''est pas identifiable.';

CREATE INDEX IF NOT EXISTS idx_fighters_current_league
    ON fighters(current_league)
    WHERE current_league IS NOT NULL;

DO $$
DECLARE
    n_total INT;
BEGIN
    SELECT COUNT(*) INTO n_total FROM fighters;
    RAISE NOTICE 'Migration 008 OK : colonne current_league creee. % fighters a backfiller via Python.', n_total;
END $$;

COMMIT;
