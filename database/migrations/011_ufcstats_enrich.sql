-- 011_ufcstats_enrich.sql
-- Colonnes d'enrichissement issues du dataset UFCStats (Kaggle).
-- Stats de frappe agregees par fighter + classification de style ML.
-- Idempotent : ADD COLUMN IF NOT EXISTS.

-- --- Stats de frappe / grappling agregees (moyennes carriere UFC) ---
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS us_avg_kd        NUMERIC;  -- knockdowns / combat
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS us_avg_str       NUMERIC;  -- frappes significatives / combat
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS us_avg_td        NUMERIC;  -- takedowns / combat
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS us_avg_sub_att   NUMERIC;  -- tentatives de soumission / combat
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS us_avg_ctrl_sec  NUMERIC;  -- temps de controle (secondes) / combat

-- Precision et repartition des frappes (ratios 0-1)
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS us_sig_str_pct   NUMERIC;
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS us_head_pct      NUMERIC;
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS us_body_pct      NUMERIC;
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS us_leg_pct       NUMERIC;
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS us_distance_pct  NUMERIC;
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS us_clinch_pct    NUMERIC;
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS us_ground_pct    NUMERIC;

-- Taux de finition par methode (sur les victoires, ratios 0-1)
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS us_ko_rate       NUMERIC;
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS us_sub_rate      NUMERIC;
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS us_dec_rate      NUMERIC;

-- --- Classification de style (label + probabilites du modele Kaggle) ---
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS fighting_style       VARCHAR;
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS style_striker        NUMERIC;
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS style_wrestler       NUMERIC;
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS style_hybrid         NUMERIC;
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS style_nostyle        NUMERIC;

-- Tracabilite : id UFCStats (hash) pour re-sync futur
ALTER TABLE fighters ADD COLUMN IF NOT EXISTS ufcstats_id          VARCHAR;
