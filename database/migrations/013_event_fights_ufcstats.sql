-- 013_event_fights_ufcstats.sql
-- Enrichissement table event_fights avec IDs UFCStats + stats per-fight cles.
-- Source : archivefg.zip (fight_details.csv + event_details.csv).
-- Idempotent : ADD COLUMN IF NOT EXISTS.

-- Tracabilite UFCStats (hash IDs officiels)
ALTER TABLE event_fights ADD COLUMN IF NOT EXISTS ufcstats_fight_id  VARCHAR;  -- hash fight UFCStats
ALTER TABLE event_fights ADD COLUMN IF NOT EXISTS ufcstats_event_id  VARCHAR;  -- hash event UFCStats

-- Stats per-fight cles (fighter1 = red/blue selon matching)
ALTER TABLE event_fights ADD COLUMN IF NOT EXISTS f1_sig_str   INTEGER;  -- sig strikes landing fighter1
ALTER TABLE event_fights ADD COLUMN IF NOT EXISTS f2_sig_str   INTEGER;  -- sig strikes landing fighter2
ALTER TABLE event_fights ADD COLUMN IF NOT EXISTS f1_td        INTEGER;  -- takedowns fighter1
ALTER TABLE event_fights ADD COLUMN IF NOT EXISTS f2_td        INTEGER;  -- takedowns fighter2
ALTER TABLE event_fights ADD COLUMN IF NOT EXISTS f1_ctrl_sec  INTEGER;  -- ctrl time (secondes) fighter1
ALTER TABLE event_fights ADD COLUMN IF NOT EXISTS f2_ctrl_sec  INTEGER;  -- ctrl time (secondes) fighter2
ALTER TABLE event_fights ADD COLUMN IF NOT EXISTS f1_kd        INTEGER;  -- knockdowns fighter1
ALTER TABLE event_fights ADD COLUMN IF NOT EXISTS f2_kd        INTEGER;  -- knockdowns fighter2
ALTER TABLE event_fights ADD COLUMN IF NOT EXISTS f1_sub_att   INTEGER;  -- sub attempts fighter1
ALTER TABLE event_fights ADD COLUMN IF NOT EXISTS f2_sub_att   INTEGER;  -- sub attempts fighter2
