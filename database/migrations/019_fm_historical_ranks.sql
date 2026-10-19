-- 019_fm_historical_ranks.sql
-- Table des classements FightMatrix HISTORIQUES (rang d'un fighter par trimestre).
--
-- POURQUOI : pour afficher le rang d'un adversaire "au moment du combat"
-- (at fight time) dans l'historique des combats. Aujourd'hui ce rang n'existe
-- que quand le scrape l'a embarque dans le nom de l'adversaire ("#105 Welter"),
-- donc tres incomplet. Cette table permet de retrouver le rang a la DATE du
-- combat pour TOUT adversaire couvert par les classements FM.
--
-- ALIMENTATION : scrapers/collect_fm_ranks.py
--   (parse les pages historiques FM, rang = position dans l'ordre de classement,
--    date deduite du numero d'issue : trimestriel depuis 1990-01-01).
--
-- LECTURE : api/app.py /api/fighters/<id>/history
--   pour chaque combat -> on cherche le rang de l'adversaire a l'issue dont la
--   date est la plus proche AVANT la date du combat.
--
-- Idempotent : CREATE TABLE IF NOT EXISTS + index IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS fm_historical_ranks (
    id            SERIAL PRIMARY KEY,
    -- cle canonique : l'URL de profil FM (toujours presente, meme si le fighter
    -- n'est pas encore en BDD). normalisee (sans trailing slash, https).
    fighter_url   TEXT    NOT NULL,
    -- resolu vers fighters.id quand on connait le fighter (sinon NULL).
    fighter_id    INTEGER REFERENCES fighters(id) ON DELETE SET NULL,
    division      TEXT    NOT NULL,   -- label FM ('Welterweight', 'Women - Strawweight'...)
    issue         INTEGER NOT NULL,   -- numero d'issue FM (1 = 1990-Q1)
    issue_date    DATE    NOT NULL,   -- date du trimestre (deduite de l'issue)
    rank          INTEGER NOT NULL,   -- rang dans la division a cette issue (1 = #1)
    created_at    TIMESTAMP DEFAULT now(),
    -- un seul rang par (fighter, division, issue). re-scraper = UPSERT.
    CONSTRAINT uq_fmhr_url_div_issue UNIQUE (fighter_url, division, issue)
);

-- jointure principale : par fighter_id + date du combat
CREATE INDEX IF NOT EXISTS idx_fmhr_fighter_id ON fm_historical_ranks (fighter_id);
-- resolution / dedoublonnage par URL
CREATE INDEX IF NOT EXISTS idx_fmhr_url        ON fm_historical_ranks (fighter_url);
-- recherche du trimestre le plus proche d'une date de combat
CREATE INDEX IF NOT EXISTS idx_fmhr_date       ON fm_historical_ranks (issue_date);

-- Verification :
-- SELECT division, issue, issue_date, count(*) FROM fm_historical_ranks
--   GROUP BY 1,2,3 ORDER BY 2 DESC LIMIT 20;
