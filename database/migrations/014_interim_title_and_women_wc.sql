-- 014_interim_title_and_women_wc.sql
-- 1. Ajoute is_interim_title sur event_fights
-- 2. Normalise les noms de divisions féminines dans fighters.weight_class_current
--    "Women Bantamweight" / "Women Flyweight" / "Women Strawweight" → "Women's ..."
-- Idempotente — safe to re-run.

-- 1. Colonne is_interim_title
ALTER TABLE event_fights
  ADD COLUMN IF NOT EXISTS is_interim_title BOOLEAN NOT NULL DEFAULT FALSE;

-- 2. Normalisation weight_class_current (manque apostrophe+s)
-- "Women Bantamweight" → "Women's Bantamweight"
-- "Women Flyweight"    → "Women's Flyweight"
-- etc.  (regexp: commence par "Women " suivi d'une majuscule, sans apostrophe)
UPDATE fighters
SET weight_class_current = 'Women''s ' || SUBSTRING(weight_class_current FROM 7)
WHERE weight_class_current ~ '^Women [A-Z]'
  AND weight_class_current NOT LIKE 'Women''s %';

-- Même chose dans weight_class_origin
UPDATE fighters
SET weight_class_origin = 'Women''s ' || SUBSTRING(weight_class_origin FROM 7)
WHERE weight_class_origin ~ '^Women [A-Z]'
  AND weight_class_origin NOT LIKE 'Women''s %';

-- 3. Normalisation dans event_fights.weight_class
UPDATE event_fights
SET weight_class = 'Women''s ' || SUBSTRING(weight_class FROM 7)
WHERE weight_class ~ '^Women [A-Z]'
  AND weight_class NOT LIKE 'Women''s %';
