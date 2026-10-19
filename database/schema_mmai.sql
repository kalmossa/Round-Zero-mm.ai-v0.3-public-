-- ============================================================================
-- MM.AI - SCHEMA POSTGRESQL
-- Auteur  : Elias Lallouet (Kalmossa)
-- Version : 7.0
--
--   Une seule table : fighters (62 colonnes)
--
--   Contraintes :
--   - id, ufc_id, fightmatrix_id, mma_com_id : tous egaux au id sequentiel
--     (rempli automatiquement apres l'INSERT par scrape_mma_supabase.py)
--   - UNIQUE (name, date_of_birth)  -> permet 2 fighters homonymes
--                                       avec dates de naissance differentes
--   - weight_class_current : DEFAULT 'Unknown' (pas de plantage si scraper rate)
--   - base_elo : NULL par defaut (rempli plus tard par le ML)
--
-- A executer dans Supabase > SQL Editor > New Query > Run
-- ATTENTION : ce script DROP tout ce qui existe (clean reset).
-- ============================================================================

DROP VIEW  IF EXISTS v_fighter_career      CASCADE;
DROP VIEW  IF EXISTS v_fighter_complete    CASCADE;
DROP TABLE IF EXISTS scouter_history       CASCADE;
DROP TABLE IF EXISTS elo_history           CASCADE;
DROP TABLE IF EXISTS predictions           CASCADE;
DROP TABLE IF EXISTS fights                CASCADE;
DROP TABLE IF EXISTS skills_profile        CASCADE;
DROP TABLE IF EXISTS external_ratings      CASCADE;
DROP TABLE IF EXISTS statistics            CASCADE;
DROP TABLE IF EXISTS fighters              CASCADE;
DROP TABLE IF EXISTS users                 CASCADE;

DROP FUNCTION IF EXISTS update_updated_at()        CASCADE;
DROP FUNCTION IF EXISTS update_fighter_age()       CASCADE;
DROP FUNCTION IF EXISTS update_days_inactive()     CASCADE;
DROP FUNCTION IF EXISTS update_total_fights()      CASCADE;
DROP FUNCTION IF EXISTS update_elo_change()        CASCADE;
DROP FUNCTION IF EXISTS update_external_elos()     CASCADE;
DROP FUNCTION IF EXISTS rank_to_elo(INT)           CASCADE;

-- ============================================================================
-- TABLE FIGHTERS (62 colonnes)
-- ============================================================================

CREATE TABLE fighters (
    id              SERIAL PRIMARY KEY,
    ufc_id          VARCHAR(80)  UNIQUE,
    fightmatrix_id  VARCHAR(80)  UNIQUE,
    mma_com_id      VARCHAR(80)  UNIQUE,

    name            VARCHAR(150) NOT NULL,
    nickname        VARCHAR(150),
    gender          VARCHAR(1)   NOT NULL DEFAULT 'M' CHECK (gender IN ('M', 'F')),
    date_of_birth   DATE,
    age             INT,
    nationality     VARCHAR(60),
    photo_url           TEXT,   -- migration 018 : TEXT (URLs CDN/data: parfois >700 chars)
    photo_thumbnail_url TEXT,   -- migration 018

    weight_class_current  VARCHAR(50) NOT NULL DEFAULT 'Unknown',
    weight_class_origin   VARCHAR(50),
    -- Colonne GENERATED STORED (migration 009) : "Flyweight M" / "Flyweight W"
    -- Postgres la recalcule automatiquement quand weight_class_current ou gender changent.
    weight_class_gendered VARCHAR(60) GENERATED ALWAYS AS (
        CASE
            WHEN weight_class_current IS NULL
              OR weight_class_current = 'Unknown'
              OR weight_class_current = ''
            THEN COALESCE(weight_class_current, 'Unknown')
            ELSE weight_class_current || ' ' || CASE gender WHEN 'F' THEN 'W' ELSE 'M' END
        END
    ) STORED,
    height_inches   VARCHAR(15),
    reach_inches    VARCHAR(15),
    stance          VARCHAR(30),
    first_sport     VARCHAR(100),

    record_total_wins   INT NOT NULL DEFAULT 0 CHECK (record_total_wins   >= 0),
    record_total_losses INT NOT NULL DEFAULT 0 CHECK (record_total_losses >= 0),
    record_total_draws  INT DEFAULT 0,
    record_total_nc     INT DEFAULT 0,
    record_ufc_wins     INT DEFAULT 0,
    record_ufc_losses   INT DEFAULT 0,
    record_ufc_draws    INT DEFAULT 0,
    record_other_wins   INT DEFAULT 0,
    record_other_losses INT DEFAULT 0,
    record_other_draws  INT DEFAULT 0,

    wins_by_ko_tko       INT DEFAULT 0,
    wins_by_submission   INT DEFAULT 0,
    wins_by_decision     INT DEFAULT 0,
    losses_by_ko_tko     INT DEFAULT 0,
    losses_by_submission INT DEFAULT 0,
    losses_by_decision   INT DEFAULT 0,

    -- Decisions partagees (split) : indicateur de "qualite" des wins/losses pour le scouter.
    -- Calcule depuis fight_history dans compute_derived() (parse_misc.py).
    split_decision_wins   INT DEFAULT 0,
    split_decision_losses INT DEFAULT 0,

    career_debut_date   DATE,
    last_fight_date     DATE,
    days_inactive       INT,
    is_active           BOOLEAN DEFAULT TRUE,
    current_league      VARCHAR(50),         -- UFC / PFL / ONE / KSW / RIZIN / Bellator / ... ; NULL si inactif ou inconnu
    is_ufc_champion     BOOLEAN DEFAULT FALSE,
    ufc_title_match_win INT DEFAULT 0,   -- total des victoires en combat de titre UFC (prise + defenses)
    total_fights        INT DEFAULT 0,
    win_percentage_int  INT,
    finish_rate_int     INT,
    current_streak      VARCHAR(15) DEFAULT '0',
    last_5_results      VARCHAR(30),
    recent_form_score   DECIMAL(4,3) CHECK (recent_form_score IS NULL OR recent_form_score BETWEEN 0 AND 1),
    base_elo            DECIMAL(7,2) CHECK (base_elo IS NULL OR base_elo BETWEEN 500 AND 3000),  -- NULL tant que le ML ne l'a pas calcule
    scouter_rating      DECIMAL(5,2) CHECK (scouter_rating IS NULL OR scouter_rating BETWEEN 0 AND 100),

    fightmatrix_rating_points     DECIMAL(7,2),
    fightmatrix_big_league_record VARCHAR(30),
    fightmatrix_540_metric        DECIMAL(7,2),
    fightmatrix_quality_perf_pct  DECIMAL(5,2),
    ufc_official_rank   INT,
    ufc_p4p_rank        INT,

    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_scraped_at TIMESTAMP,
    data_source     TEXT,
    data_quality_score INT DEFAULT 0 CHECK (data_quality_score BETWEEN 0 AND 100),
    is_verified     BOOLEAN DEFAULT FALSE,
    notes           TEXT,
    fight_history   TEXT,

    CONSTRAINT uq_fighter_name_dob UNIQUE (name, date_of_birth)
);

CREATE INDEX idx_fighters_name          ON fighters(name);
CREATE INDEX idx_fighters_weight_class  ON fighters(weight_class_current);
CREATE INDEX idx_fighters_weight_class_gendered ON fighters(weight_class_gendered)
    WHERE weight_class_gendered IS NOT NULL AND weight_class_gendered != 'Unknown';
CREATE INDEX idx_fighters_nationality   ON fighters(nationality);
CREATE INDEX idx_fighters_base_elo      ON fighters(base_elo DESC);
CREATE INDEX idx_fighters_scouter       ON fighters(scouter_rating DESC NULLS LAST);
CREATE INDEX idx_fighters_active        ON fighters(is_active) WHERE is_active = TRUE;
CREATE INDEX idx_fighters_champion      ON fighters(is_ufc_champion) WHERE is_ufc_champion = TRUE;
CREATE INDEX idx_fighters_last_fight    ON fighters(last_fight_date DESC);
CREATE INDEX idx_fighters_current_league ON fighters(current_league) WHERE current_league IS NOT NULL;

-- ============================================================================
-- TRIGGERS
-- ============================================================================

CREATE OR REPLACE FUNCTION update_updated_at() RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = CURRENT_TIMESTAMP; RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_fighters_updated_at
    BEFORE UPDATE ON fighters FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE OR REPLACE FUNCTION update_fighter_age() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.date_of_birth IS NOT NULL THEN
        NEW.age := EXTRACT(YEAR FROM AGE(CURRENT_DATE, NEW.date_of_birth))::INT;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_fighters_age
    BEFORE INSERT OR UPDATE OF date_of_birth ON fighters
    FOR EACH ROW EXECUTE FUNCTION update_fighter_age();

CREATE OR REPLACE FUNCTION update_days_inactive() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.last_fight_date IS NOT NULL THEN
        NEW.days_inactive := CURRENT_DATE - NEW.last_fight_date;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_fighters_inactivite
    BEFORE INSERT OR UPDATE OF last_fight_date ON fighters
    FOR EACH ROW EXECUTE FUNCTION update_days_inactive();

CREATE OR REPLACE FUNCTION update_total_fights() RETURNS TRIGGER AS $$
BEGIN
    NEW.total_fights := COALESCE(NEW.record_total_wins, 0)
                      + COALESCE(NEW.record_total_losses, 0)
                      + COALESCE(NEW.record_total_draws, 0);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_fighters_total_fights
    BEFORE INSERT OR UPDATE OF record_total_wins, record_total_losses, record_total_draws ON fighters
    FOR EACH ROW EXECUTE FUNCTION update_total_fights();

SELECT
    'Schema MM.AI v7.0 cree avec succes' AS message,
    (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='fighters') AS nb_colonnes_fighters;
