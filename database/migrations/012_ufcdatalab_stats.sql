-- 012_ufcdatalab_stats.sql
-- Colonnes supplementaires issues de UFC-DataLab (raw_fighter_details.csv).
-- Metriques manquantes dans le dataset Kaggle 1 (011_ufcstats_enrich.sql).
-- Idempotent : ADD COLUMN IF NOT EXISTS.

-- Frappes : per-minute (format standard UFC Stats officiel)
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS us_slpm       NUMERIC;  -- Sig. Str. Landed per Min
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS us_sapm       NUMERIC;  -- Sig. Str. Absorbed per Min

-- Defense
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS us_str_def    NUMERIC;  -- Striking Defense (0-1)
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS us_td_def     NUMERIC;  -- Takedown Defense (0-1)

-- Takedown accuracy
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS us_td_acc     NUMERIC;  -- Takedown Accuracy (0-1)
