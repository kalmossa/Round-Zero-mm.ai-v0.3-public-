-- ============================================================================
-- MM.AI - Migration 006 : ufc_title_defenses -> ufc_title_match_win
-- Version : 3.2
-- Date    : 2026-05-20
--
-- CHANGEMENT SEMANTIQUE :
--   Avant : ufc_title_defenses = nombre de defenses de ceinture
--           (1ere victoire = prise de titre, les suivantes = defenses)
--           Formule scraper : defenses = max(0, title_wins - 1)
--
--   Apres : ufc_title_match_win = total des victoires en combat de titre UFC
--           (prise de titre + defenses, toutes les W en championship match)
--           Formule scraper : ufc_title_match_win = title_wins
--
-- Plus fidele a "Title Bouts: X-Y-Z" de FightMatrix qui compte directement le X.
-- Plus interpretable pour les utilisateurs ("4 combats de titre gagnes" vs
-- "3 defenses, en oubliant la prise").
--
-- ROLLBACK : remplacer dans cette migration :
--   ALTER TABLE fighters RENAME COLUMN ufc_title_match_win TO ufc_title_defenses;
--   UPDATE fighters SET ufc_title_match_win = GREATEST(0, ufc_title_match_win - 1)
--   -- (impossible a inverser exactement si certains champs etaient deja a 0)
-- ============================================================================

BEGIN;

-- 1. Rename
ALTER TABLE fighters
    RENAME COLUMN ufc_title_defenses TO ufc_title_match_win;

-- 2. Recompute des valeurs existantes :
--    L'ancienne convention stockait (title_wins - 1).
--    La nouvelle convention stocke title_wins.
--    Pour les fighters qui ont au moins 1 victoire de titre (champions ou ex-champions),
--    on AJOUTE 1 a la valeur existante (pour reconstituer title_wins).
--    Les fighters n'ayant jamais eu de combat de titre (ufc_title_defenses = 0)
--    restent a 0.
UPDATE fighters
SET ufc_title_match_win = ufc_title_match_win + 1
WHERE ufc_title_match_win > 0
   OR is_ufc_champion = TRUE;

-- 3. Verification
DO $$
DECLARE
    cnt_champ INT;
    cnt_with_wins INT;
BEGIN
    SELECT COUNT(*) INTO cnt_champ
    FROM fighters
    WHERE is_ufc_champion = TRUE;

    SELECT COUNT(*) INTO cnt_with_wins
    FROM fighters
    WHERE ufc_title_match_win > 0;

    RAISE NOTICE 'Migration 006 OK : % champions actuels, % fighters avec >=1 title match win',
        cnt_champ, cnt_with_wins;
END $$;

COMMIT;
