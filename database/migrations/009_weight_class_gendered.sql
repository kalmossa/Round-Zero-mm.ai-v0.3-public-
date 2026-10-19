-- ============================================================================
-- MM.AI - Migration 009 : colonne generee weight_class_gendered
-- Version : 3.4
-- Date    : 2026-05-21
--
-- CONTEXTE :
--   Une categorie de poids n'existe pas dans le vide en MMA : "Flyweight" homme
--   et "Flyweight" femme sont 2 divisions distinctes (poids identiques mais
--   competitions, rankings, champions, P4P separes). Sans ce suffixe, impossible
--   de filtrer correctement les rankings (sinon Shevchenko apparait dans la
--   meme division que Pantoja par exemple).
--
-- ACTION :
--   1. ALTER TABLE : ajoute weight_class_gendered en colonne GENERATED STORED,
--      derivee automatiquement de weight_class_current + gender.
--   2. Index pour requetes du type "donne-moi tous les Flyweight W".
--
-- VALEURS PRODUITES :
--   gender='M' + weight_class_current='Flyweight'  -> 'Flyweight M'
--   gender='F' + weight_class_current='Flyweight'  -> 'Flyweight W'
--   gender='F' + weight_class_current='Strawweight'-> 'Strawweight W'
--   weight_class_current='Unknown'                 -> 'Unknown'
--
-- AVANTAGE GENERATED COLUMN :
--   Pas besoin de scraper ni de backfill : Postgres recalcule a chaque
--   INSERT/UPDATE de weight_class_current ou gender. Aucune desynchronisation.
--
-- REVERSIBLE :
--   ALTER TABLE fighters DROP COLUMN weight_class_gendered;
--   DROP INDEX idx_fighters_weight_class_gendered;
-- ============================================================================

BEGIN;

ALTER TABLE fighters
    ADD COLUMN IF NOT EXISTS weight_class_gendered VARCHAR(60)
        GENERATED ALWAYS AS (
            CASE
                WHEN weight_class_current IS NULL
                  OR weight_class_current = 'Unknown'
                  OR weight_class_current = ''
                THEN COALESCE(weight_class_current, 'Unknown')
                ELSE weight_class_current
                     || ' '
                     || CASE gender WHEN 'F' THEN 'W' ELSE 'M' END
            END
        ) STORED;

COMMENT ON COLUMN fighters.weight_class_gendered IS
    'Categorie de poids genree : Flyweight M / Flyweight W / Strawweight W ... '
    'Colonne GENERATED STORED : Postgres la recalcule automatiquement a partir '
    'de weight_class_current et gender. Source de verite pour le frontend.';

CREATE INDEX IF NOT EXISTS idx_fighters_weight_class_gendered
    ON fighters(weight_class_gendered)
    WHERE weight_class_gendered IS NOT NULL AND weight_class_gendered != 'Unknown';

DO $$
DECLARE
    n_total INT;
    n_w INT;
    n_m INT;
BEGIN
    SELECT COUNT(*) INTO n_total FROM fighters;
    SELECT COUNT(*) INTO n_w FROM fighters WHERE gender = 'F';
    SELECT COUNT(*) INTO n_m FROM fighters WHERE gender = 'M';
    RAISE NOTICE 'Migration 009 OK : weight_class_gendered creee. % fighters (% H / % F).', n_total, n_m, n_w;
END $$;

COMMIT;
